from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts'
MANIFEST_PATH = ARTIFACTS / 'split_release_manifest.json'
ARCHIVE_PATH = ARTIFACTS / 'embodied-arm-split-release.zip'
EXCLUDED_PARTS = {'__pycache__', '.pytest_cache', 'node_modules', '.pio', 'build', 'install', 'log', 'artifacts'}
EXCLUDED_SUFFIXES = {'.pyc', '.tsbuildinfo', '.zip'}
EXCLUDED_PREFIXES = {
    Path('upper_computer/backend/embodied_arm_ws/src/arm_hmi'),
    Path('upper_computer/backend/embodied_arm_ws/src/arm_task_manager'),
    Path('upper_computer/backend/embodied_arm_ws/src/arm_motion_bridge'),
    Path('upper_computer/backend/embodied_arm_ws/src/arm_vision'),
    Path('upper_computer/backend/embodied_arm_ws/tests/test_deprecated_packages.py'),
    Path('upper_computer/backend/embodied_arm_ws/tests/test_target_architecture_packages.py'),
}


def _is_relative_to(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix)
        return True
    except ValueError:
        return False


def iter_release_files():
    for path in sorted(ROOT.rglob('*')):
        if path.is_dir():
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if any(_is_relative_to(rel, prefix) for prefix in EXCLUDED_PREFIXES):
            continue
        if rel.suffix in EXCLUDED_SUFFIXES:
            continue
        yield path


def read_protocol_version() -> str:
    protocol = ROOT / 'stm32f103c8_platformio/include/protocol.hpp'
    text = protocol.read_text(encoding='utf-8')
    for marker in ('constexpr uint8_t kProtocolVersion =', '#define PROTOCOL_VERSION'):
        if marker in text:
            return text.split(marker, 1)[1].split(';', 1)[0].split('\n', 1)[0].strip().strip('"')
    return '1'



def read_esp32_firmware_semantic_manifest() -> dict:
    manifest_path = ROOT / 'upper_computer/backend/embodied_arm_ws/src/arm_bringup/config/firmware_semantic_profiles.yaml'
    header_path = ROOT / 'esp32s3_platformio/include/generated/runtime_semantic_profile.hpp'
    payload = yaml.safe_load(manifest_path.read_text(encoding='utf-8')) or {}
    esp32 = payload.get('esp32', {}) if isinstance(payload, dict) else {}
    checksum = hashlib.sha256(manifest_path.read_bytes() + b'\n' + header_path.read_bytes()).hexdigest()
    return {
        'manifestPath': str(manifest_path.relative_to(ROOT)),
        'generatedHeaderPath': str(header_path.relative_to(ROOT)),
        'defaultProfile': str(esp32.get('default_profile', '')),
        'profiles': sorted((esp32.get('profiles') or {}).keys()),
        'semanticChecksum': checksum,
    }

def build_manifest() -> dict:
    files = [str(path.relative_to(ROOT)) for path in iter_release_files()]
    files.append('artifacts/split_release_manifest.json')
    third_party_inventory = {
        'license': 'LICENSE',
        'notices': 'THIRD_PARTY_NOTICES.md',
        'upstreamIndex': 'third_party/UPSTREAM_INDEX.md',
        'vendoredModules': [],
    }
    return {
        'systemVersion': 'split-delivery-v1',
        'upperComputerVersion': 'upper_computer@split',
        'esp32FirmwareVersion': 'esp32s3_platformio@split',
        'stm32FirmwareVersion': 'stm32f103c8_platformio@split',
        'protocolVersion': read_protocol_version(),
        'compatibility': {
            'targetOS': 'Ubuntu 22.04 LTS',
            'targetROS2': 'Humble',
            'firmwareTransport': ['serial', 'wifi'],
        },
        'firmwareSemanticContract': read_esp32_firmware_semantic_manifest(),
        'thirdPartyGovernance': {
            'inventoryMode': 'reference_only',
            'noticeFile': 'THIRD_PARTY_NOTICES.md',
            'upstreamIndex': 'third_party/UPSTREAM_INDEX.md',
        },
        'thirdPartyInventory': third_party_inventory,
        'fileCount': len(files),
        'files': files,
    }


def write_manifest_and_archive(manifest: dict) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with zipfile.ZipFile(ARCHIVE_PATH, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for path in iter_release_files():
            zf.write(path, arcname=str(path.relative_to(ROOT)))
        zf.write(MANIFEST_PATH, arcname='artifacts/split_release_manifest.json')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--write-manifest-on-check', action='store_true')
    args = parser.parse_args()
    manifest = build_manifest()
    if args.check:
        if MANIFEST_PATH.exists():
            existing = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
            if existing != manifest:
                raise SystemExit('split release manifest is stale')
            print('split release manifest check passed')
            return 0
        if args.write_manifest_on_check:
            ARTIFACTS.mkdir(parents=True, exist_ok=True)
            MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
            print('split release manifest check passed (manifest regenerated in clean checkout)')
            return 0
        print('split release manifest check passed (clean checkout: manifest regenerated in-memory)')
        return 0
    write_manifest_and_archive(manifest)
    print(f'wrote {MANIFEST_PATH}')
    print(f'wrote {ARCHIVE_PATH}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
