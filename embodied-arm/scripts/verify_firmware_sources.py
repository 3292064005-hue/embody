#!/usr/bin/env python3
"""Validate split firmware source contracts without requiring toolchain downloads."""
from __future__ import annotations

import ast
import configparser
import json
import re
import sys

import yaml
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT_DIR / 'artifacts' / 'split_repository_validation'
ARTIFACT_PATH = ARTIFACT_DIR / 'firmware_source_validation.json'
ESP32_DIR = ROOT_DIR / 'esp32s3_platformio'
FIRMWARE_SEMANTIC_PROFILES = ROOT_DIR / 'upper_computer' / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'firmware_semantic_profiles.yaml'
STM32_DIR = ROOT_DIR / 'stm32f103c8_platformio'
PY_ENUMS = ROOT_DIR / 'upper_computer' / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_backend_common' / 'arm_backend_common' / 'enums.py'
SERIAL_DOC = ROOT_DIR / 'upper_computer' / 'docs' / 'SERIAL_PROTOCOL.md'
FIRMWARE_INTEGRATION_DOC = ROOT_DIR / 'upper_computer' / 'docs' / 'FIRMWARE_SPLIT_INTEGRATION.md'


class ValidationError(RuntimeError):
    """Raised when the firmware source contract is inconsistent."""


def _validate_esp32_semantic_contract() -> dict[str, object]:
    project_config = _read(ESP32_DIR / 'include' / 'project_config.hpp')
    generated_header = _read(ESP32_DIR / 'include' / 'generated' / 'runtime_semantic_profile.hpp')
    platformio_ini = _read(ESP32_DIR / 'platformio.ini')
    semantic_payload = yaml.safe_load(_read(FIRMWARE_SEMANTIC_PROFILES)) or {}
    esp32_payload = semantic_payload.get('esp32', {}) if isinstance(semantic_payload, dict) else {}
    default_profile = str(esp32_payload.get('default_profile', '') or '').strip()
    profiles = esp32_payload.get('profiles', {}) if isinstance(esp32_payload.get('profiles'), dict) else {}
    _require(default_profile in profiles, 'firmware_semantic_profiles.yaml default_profile must reference one declared profile')
    _require('#include "generated/runtime_semantic_profile.hpp"' in project_config, 'ESP32 project_config.hpp must include generated/runtime_semantic_profile.hpp')
    _require('EMBODIED_ARM_DEFAULT_STREAM_SEMANTIC' in project_config, 'ESP32 project_config.hpp must consume generated semantic defaults')
    macro_name = f'EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE_{default_profile.upper()}'
    _require(macro_name in generated_header, f'generated runtime semantic header missing macro {macro_name}')
    _require(f'-DEMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE={macro_name}' in platformio_ini, 'platformio.ini must pin the default runtime semantic profile macro')
    return {'defaultProfile': default_profile, 'profileCount': len(profiles), 'macro': macro_name}


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _validate_required_files(base_dir: Path, relative_paths: Iterable[str]) -> list[str]:
    missing = [relative_path for relative_path in relative_paths if not (base_dir / relative_path).exists()]
    _require(not missing, f"missing required files under {base_dir.name}: {', '.join(missing)}")
    return list(relative_paths)


def _load_platformio_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(path, encoding='utf-8')
    return parser


def _enum_members_from_cpp(header_text: str, enum_name: str) -> dict[str, int]:
    pattern = rf"enum class\s+{re.escape(enum_name)}\s*:\s*uint8_t\s*{{(?P<body>.*?)}};"
    match = re.search(pattern, header_text, flags=re.S)
    _require(match is not None, f'failed to locate C++ enum {enum_name}')
    members: dict[str, int] = {}
    for raw_line in match.group('body').splitlines():
        line = raw_line.split('//', 1)[0].strip().rstrip(',')
        if not line:
            continue
        name, _, value_expr = line.partition('=')
        _require(bool(name.strip() and value_expr.strip()), f'invalid enum entry in {enum_name}: {raw_line!r}')
        members[name.strip()] = int(value_expr.strip(), 0)
    return members


def _enum_members_from_python(path: Path, enum_name: str) -> dict[str, int]:
    tree = ast.parse(_read(path), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == enum_name:
            members: dict[str, int] = {}
            for statement in node.body:
                if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
                    members[statement.targets[0].id] = int(ast.literal_eval(statement.value))
            _require(bool(members), f'python enum {enum_name} is empty')
            return members
    raise ValidationError(f'failed to locate python enum {enum_name}')


def _extract_route_constants(project_config_text: str) -> dict[str, str]:
    constants: dict[str, str] = {}
    for name in ('kStreamPath', 'kVoiceEventsPath', 'kVoicePhrasePath', 'kVoiceCommandsPath', 'kHealthPath', 'kStatusPath'):
        match = re.search(rf'{name}\[]\s*=\s*"([^"]+)"', project_config_text)
        _require(match is not None, f'missing ESP32 route constant {name}')
        constants[name] = match.group(1)
    return constants


def _validate_esp32_routes() -> dict[str, object]:
    project_config = _read(ESP32_DIR / 'include' / 'project_config.hpp')
    main_cpp = _read(ESP32_DIR / 'src' / 'main.cpp')
    integration_doc = _read(FIRMWARE_INTEGRATION_DOC)
    route_constants = _extract_route_constants(project_config)
    for constant_name, route in route_constants.items():
        _require(route.startswith('/'), f"ESP32 route must start with '/': {constant_name}={route}")
        _require(constant_name in main_cpp, f'ESP32 main.cpp does not reference route constant {constant_name}')
        _require(route in integration_doc, f'FIRMWARE_SPLIT_INTEGRATION.md missing documented route {route}')
    for registration in ('server_.on(kHealthPath', 'server_.on(kStatusPath', 'server_.on(kVoiceEventsPath', 'server_.on(kVoiceCommandsPath', 'server_.on(kVoicePhrasePath', 'server_.on(kStreamPath'):
        _require(registration in main_cpp, f'ESP32 firmware missing route registration: {registration}')
    return {'routes': route_constants, 'integrationDocChecked': True}


def _extract_sequence_width_from_doc(serial_doc: str) -> str:
    match = re.search(r'-\s+Sequence:\s+`([^`]+)`', serial_doc)
    _require(match is not None, 'SERIAL_PROTOCOL.md missing Sequence field declaration')
    return match.group(1).strip()


def _validate_serial_protocol_contract() -> dict[str, object]:
    serial_doc = _read(SERIAL_DOC)
    cpp_members = _enum_members_from_cpp(_read(STM32_DIR / 'include' / 'protocol.hpp'), 'HardwareCommand')
    py_members = _enum_members_from_python(PY_ENUMS, 'HardwareCommand')
    canonical_python_members = {name: value for name, value in py_members.items() if name != 'JOG_JOINT'}
    _require(cpp_members == canonical_python_members, f'HardwareCommand mismatch between STM32 and Python enums: {cpp_members} != {canonical_python_members}')
    for command_name in cpp_members:
        _require(f'`{command_name}`' in serial_doc, f'SERIAL_PROTOCOL.md missing command {command_name}')
    _require(_extract_sequence_width_from_doc(serial_doc) == 'uint8', 'SERIAL_PROTOCOL.md sequence width is inconsistent with code (expected uint8)')
    _require('旧文档中出现过 `ESTOP / SAFE_HALT / JOG / GRIPPER`' in serial_doc, 'SERIAL_PROTOCOL.md lost the explicit legacy-command warning')
    _require('result_code' in serial_doc, 'SERIAL_PROTOCOL.md missing result_code execution feedback field')
    _require('execution_state' in serial_doc, 'SERIAL_PROTOCOL.md missing execution_state execution feedback field')
    return {'cppCommands': cpp_members, 'pythonCommands': canonical_python_members, 'sequenceField': 'uint8', 'feedbackFields': ['result_code', 'execution_state']}


def _validate_platformio_project(path: Path, expected_section: str, expected_pairs: dict[str, str]) -> dict[str, object]:
    parser = _load_platformio_ini(path / 'platformio.ini')
    _require(parser.has_section('platformio'), f'{path.name} platformio.ini missing [platformio] section')
    _require(parser.has_section(expected_section), f'{path.name} platformio.ini missing [{expected_section}] section')
    section = parser[expected_section]
    for key, expected_value in expected_pairs.items():
        actual_value = section.get(key)
        _require(actual_value == expected_value, f"{path.name} platformio.ini mismatch for {key}: expected {expected_value!r}, got {actual_value!r}")
    return {'defaultEnv': parser['platformio'].get('default_envs'), 'section': expected_section, 'settings': {key: section.get(key) for key in expected_pairs}}


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        'esp32': {
            'requiredFiles': _validate_required_files(ESP32_DIR, ['platformio.ini', 'src/main.cpp', 'include/board_state.hpp', 'include/project_config.hpp', 'partitions/esp32s3_n16r8_littlefs.csv']),
            'platformio': _validate_platformio_project(ESP32_DIR, 'env:esp32s3_n16r8', {'platform': 'espressif32', 'board': 'esp32s3_n16r8', 'framework': 'arduino'}),
            'routes': _validate_esp32_routes(),
            'semanticContract': _validate_esp32_semantic_contract(),
        },
        'stm32': {
            'requiredFiles': _validate_required_files(STM32_DIR, ['platformio.ini', 'src/main.cpp', 'src/protocol.cpp', 'include/protocol.hpp', 'include/state.hpp', 'include/project_config.hpp']),
            'platformio': _validate_platformio_project(STM32_DIR, 'env:bluepill_f103c8', {'platform': 'ststm32', 'board': 'bluepill_f103c8', 'framework': 'arduino'}),
            'serialProtocol': _validate_serial_protocol_contract(),
        },
    }
    ARTIFACT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'firmware source validation passed -> {ARTIFACT_PATH}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f'firmware source validation failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
