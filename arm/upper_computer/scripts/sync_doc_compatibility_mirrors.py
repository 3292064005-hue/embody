from __future__ import annotations

"""Generate compatibility mirrors for legacy documentation entrypoints.

These mirrors keep machine-readable legacy paths stable while the canonical
narrative documentation lives under ``docs/interfaces`` / ``docs/operations`` /
``docs/evidence``. The mirrors are intentionally generated so scripts and audit
checks can consume them without relying on human-authored prose structure.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DOCS = ROOT / 'docs'
GENERATED = DOCS / 'generated'
MANIFEST_PATH = GENERATED / 'doc_compatibility_manifest.json'

def _resolve_repo_peer_path(*parts: str) -> Path:
    primary = REPO_ROOT.joinpath(*parts)
    if primary.exists():
        return primary
    return ROOT.joinpath(*parts)

ESP32_PROJECT_CONFIG = _resolve_repo_peer_path('esp32s3_platformio', 'include', 'project_config.hpp')
STM32_PROTOCOL = _resolve_repo_peer_path('stm32f103c8_platformio', 'include', 'protocol.hpp')
PY_ENUMS = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_backend_common' / 'arm_backend_common' / 'enums.py'
FRONTEND_LEDGER = ROOT / 'artifacts' / 'release_gates' / 'frontend_validation_ledger.json'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()

def _missing_dependency_issue(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    return f'documentation compatibility mirror dependency unavailable: {message}'


def _safe_render_outputs() -> tuple[dict[Path, str], list[str]]:
    try:
        return render_outputs(), []
    except Exception as exc:
        return {}, [_missing_dependency_issue(exc)]


def _extract_esp32_routes() -> dict[str, str]:
    text = _read(ESP32_PROJECT_CONFIG)
    constants: dict[str, str] = {}
    for name in ('kStreamPath', 'kVoiceEventsPath', 'kVoicePhrasePath', 'kVoiceCommandsPath', 'kHealthPath', 'kStatusPath'):
        match = re.search(rf'{name}\[]\s*=\s*"([^"]+)"', text)
        if match is None:
            raise RuntimeError(f'missing ESP32 route constant {name}')
        constants[name] = match.group(1)
    return constants


def _extract_cpp_enum(enum_name: str, text: str) -> dict[str, int]:
    pattern = rf"enum class\s+{re.escape(enum_name)}\s*:\s*uint8_t\s*{{(?P<body>.*?)}};"
    match = re.search(pattern, text, flags=re.S)
    if match is None:
        raise RuntimeError(f'failed to locate enum {enum_name}')
    members: dict[str, int] = {}
    for raw_line in match.group('body').splitlines():
        line = raw_line.split('//', 1)[0].strip().rstrip(',')
        if not line:
            continue
        name, _, value = line.partition('=')
        if not name.strip() or not value.strip():
            raise RuntimeError(f'invalid enum line in {enum_name}: {raw_line!r}')
        members[name.strip()] = int(value.strip(), 0)
    return members


def _extract_python_hardware_commands() -> dict[str, int]:
    text = _read(PY_ENUMS)
    class_match = re.search(r'class\s+HardwareCommand\(IntEnum\):(?P<body>.*?)(?:\n\nclass\s|\Z)', text, flags=re.S)
    if class_match is None:
        raise RuntimeError('failed to locate python HardwareCommand enum')
    members: dict[str, int] = {}
    for raw_line in class_match.group('body').splitlines():
        line = raw_line.split('#', 1)[0].strip()
        if not line or '=' not in line:
            continue
        name, value = [item.strip() for item in line.split('=', 1)]
        members[name] = int(value, 0)
    members.pop('JOG_JOINT', None)
    return members


def _load_frontend_ledger() -> dict[str, Any]:
    if not FRONTEND_LEDGER.exists():
        return {'overallStatus': 'not_executed', 'matrix': []}
    try:
        payload = json.loads(FRONTEND_LEDGER.read_text(encoding='utf-8'))
    except Exception:
        return {'overallStatus': 'not_executed', 'matrix': []}
    return payload if isinstance(payload, dict) else {'overallStatus': 'not_executed', 'matrix': []}


COMPATIBILITY_SPECS: tuple[dict[str, str], ...] = (
    {
        'legacy': 'docs/FIRMWARE_SPLIT_INTEGRATION.md',
        'canonical': 'docs/operations/firmware-integration.md',
        'scope': 'firmware_routes_and_split_responsibilities',
        'generator': 'upper_computer/scripts/sync_doc_compatibility_mirrors.py',
    },
    {
        'legacy': 'docs/SERIAL_PROTOCOL.md',
        'canonical': 'docs/interfaces/stm32-serial-protocol.md',
        'scope': 'stm32_serial_contract_and_command_ids',
        'generator': 'upper_computer/scripts/sync_doc_compatibility_mirrors.py',
    },
    {
        'legacy': 'docs/FRONTEND_VALIDATION_STATUS.md',
        'canonical': 'docs/evidence/frontend-validation-status.md',
        'scope': 'frontend_validation_matrix_and_release_evidence',
        'generator': 'upper_computer/scripts/sync_doc_compatibility_mirrors.py',
    },
    {
        'legacy': 'docs/CONTRACT_INDEX.md',
        'canonical': 'docs/interfaces/api-contract.md',
        'scope': 'generated_contract_index_and_runtime_contract_artifacts',
        'generator': 'upper_computer/scripts/generate_contract_artifacts.py',
    },
    {
        'legacy': 'docs/ROS2_INTERFACE_INDEX.md',
        'canonical': 'docs/interfaces/ros2-interface-index.md',
        'scope': 'generated_ros2_interface_index_and_runtime_lane_projection',
        'generator': 'upper_computer/scripts/generate_contract_artifacts.py',
    },
)


def build_firmware_mirror() -> str:
    routes = _extract_esp32_routes()
    route_lines = '\n'.join(f'- `{name}` → `{route}`' for name, route in routes.items())
    return '\n'.join(
        [
            '# Firmware Split Integration',
            '',
            '> Status: generated compatibility mirror',
            '> Canonical narrative documentation: `docs/operations/firmware-integration.md`',
            '> Generator: `upper_computer/scripts/sync_doc_compatibility_mirrors.py`',
            '> This file remains machine-readable for split repository checks and legacy consumers. Do not replace it with a pointer page.',
            '',
            'Use the canonical operations document for ownership, rollout order, and narrative integration guidance. This mirror exists because release gates still consume the legacy `docs/FIRMWARE_SPLIT_INTEGRATION.md` path.',
            '',
            '## Canonical source mapping',
            '- canonical document: `docs/operations/firmware-integration.md`',
            '- split verification script: `scripts/verify_firmware_sources.py`',
            '',
            '## ESP32 HTTP route contract',
            route_lines,
            '',
            '## Split responsibilities',
            '- ESP32-S3: Wi-Fi / endpoint reachability / board health / metadata bridge / voice-observability ingress',
            '- STM32F103C8: serial protocol / ACK-NACK / state and fault reporting / dispatcher-facing execution transport',
            '',
            '## Integration chain',
            '`gateway -> ROS2 backend -> dispatcher / bridge -> firmware protocol / transport -> firmware`',
            '',
            '## Documentation contract',
            '- Legacy path remains a generated compatibility mirror.',
            '- Canonical prose and ownership stay in `docs/operations/firmware-integration.md`.',
            '- Route additions or removals must update firmware code and regenerate this mirror in the same change.',
            '',
        ]
    )


def build_serial_mirror() -> str:
    cpp_members = _extract_cpp_enum('HardwareCommand', _read(STM32_PROTOCOL))
    py_members = _extract_python_hardware_commands()
    if cpp_members != py_members:
        raise RuntimeError(f'HardwareCommand mismatch while generating mirror: {cpp_members!r} != {py_members!r}')
    command_lines = '\n'.join(f'- `{name}` = `0x{value:02X}`' for name, value in cpp_members.items())
    return '\n'.join(
        [
            '# Serial Protocol',
            '',
            '> Status: generated compatibility mirror',
            '> Canonical narrative documentation: `docs/interfaces/stm32-serial-protocol.md`',
            '> Generator: `upper_computer/scripts/sync_doc_compatibility_mirrors.py`',
            '> This file remains machine-readable for firmware/source contract checks and compatibility consumers. Do not replace it with a pointer page.',
            '',
            'Use the canonical interface document for ownership, transport semantics, and integration guidance. This mirror exists because release gates still consume the legacy `docs/SERIAL_PROTOCOL.md` path.',
            '',
            '## Frame fields',
            '- SOF: `0xAA55`',
            '- Command: `HardwareCommand` enum payload',
            '- Sequence: `uint8`',
            '- Payload: JSON string encoded by firmware/backend shared helpers',
            '- Feedback fields: `result_code`, `execution_state`',
            '',
            '## Command IDs',
            command_lines,
            '',
            '## Compatibility warning',
            '旧文档中出现过 `ESTOP / SAFE_HALT / JOG / GRIPPER`，这些名字不再作为当前权威命令字面量；兼容解释必须回落到当前 `HardwareCommand` 枚举与 canonical 文档。',
            '',
            '## Documentation contract',
            '- Canonical narrative path: `docs/interfaces/stm32-serial-protocol.md`',
            '- Machine-readable mirror path: `docs/SERIAL_PROTOCOL.md`',
            '- Firmware/backend enum drift must be fixed before this mirror can be regenerated.',
            '',
        ]
    )


def build_frontend_validation_mirror() -> str:
    ledger = _load_frontend_ledger()
    matrix = ledger.get('matrix', []) if isinstance(ledger.get('matrix'), list) else []
    rendered_matrix = [
        '| Step | Status | Required | Log |',
        '|---|---|---|---|',
    ]
    for item in matrix:
        if not isinstance(item, dict):
            continue
        label = str(item.get('label', item.get('step', '')) or '')
        status = str(item.get('status', 'not_executed') or 'not_executed')
        required = 'yes' if bool(item.get('required', True)) else 'no'
        log_path = str(item.get('logPath', '') or '').strip() or '-'
        rendered_matrix.append(f'| {label} | `{status}` | {required} | `{log_path}` |')
    if len(rendered_matrix) == 2:
        rendered_matrix.append('| frontend validation | `not_executed` | yes | `-` |')
    return '\n'.join(
        [
            '# Frontend Validation Status',
            '',
            '> Status: generated compatibility mirror',
            '> Canonical evidence document: `docs/evidence/frontend-validation-status.md`',
            '> Generator: `upper_computer/scripts/sync_doc_compatibility_mirrors.py`',
            '',
            'This mirror keeps the legacy `docs/FRONTEND_VALIDATION_STATUS.md` entrypoint readable. The canonical evidence file and machine-readable ledger remain authoritative.',
            '',
            f"- overall status: `{str(ledger.get('overallStatus', 'not_executed') or 'not_executed')}`",
            f"- machine-readable ledger: `{_relative(FRONTEND_LEDGER) if FRONTEND_LEDGER.exists() else 'artifacts/release_gates/frontend_validation_ledger.json'}`",
            '',
            *rendered_matrix,
            '',
        ]
    )


def build_manifest() -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for spec in COMPATIBILITY_SPECS:
        entries.append(
            {
                'legacyPath': spec['legacy'],
                'canonicalPath': spec['canonical'],
                'status': 'generated compatibility mirror',
                'generator': spec['generator'],
                'scope': spec['scope'],
            }
        )
    return {
        'schemaVersion': 1,
        'generatedBy': 'upper_computer/scripts/sync_doc_compatibility_mirrors.py',
        'entries': entries,
    }


def render_outputs() -> dict[Path, str]:
    return {
        DOCS / 'FIRMWARE_SPLIT_INTEGRATION.md': build_firmware_mirror() + '\n',
        DOCS / 'SERIAL_PROTOCOL.md': build_serial_mirror() + '\n',
        DOCS / 'FRONTEND_VALIDATION_STATUS.md': build_frontend_validation_mirror() + '\n',
        MANIFEST_PATH: json.dumps(build_manifest(), ensure_ascii=False, indent=2) + '\n',
    }


def check_outputs() -> list[str]:
    outputs, issues = _safe_render_outputs()
    if issues:
        return issues
    for path, expected in outputs.items():
        if not path.exists():
            issues.append(f'missing generated compatibility mirror: {_relative(path)}')
            continue
        current = path.read_text(encoding='utf-8')
        if current != expected:
            issues.append(f'generated compatibility mirror drift: {_relative(path)}')
    return issues


def write_outputs() -> None:
    outputs, issues = _safe_render_outputs()
    if issues:
        raise RuntimeError('\n'.join(issues))
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate or verify legacy documentation compatibility mirrors.')
    parser.add_argument('--check', action='store_true', help='Fail if generated compatibility mirrors are stale.')
    args = parser.parse_args()
    if args.check:
        issues = check_outputs()
        if issues:
            raise SystemExit('\n'.join(issues))
        print('documentation compatibility mirrors are in sync')
        return 0
    write_outputs()
    print('documentation compatibility mirrors updated')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
