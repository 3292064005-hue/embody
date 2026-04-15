#!/usr/bin/env python3
from __future__ import annotations

"""Synchronize derived runtime config files from the canonical runtime authority."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime_authority import (
    ESP32_FIRMWARE_PROFILE_HEADER_PATH,
    FIRMWARE_SEMANTIC_PROFILES_PATH,
    PLANNING_BACKEND_PROFILES_PATH,
    RUNTIME_LANE_ALIASES_PATH,
    RUNTIME_PROFILES_PATH,
    RUNTIME_PROMOTION_RECEIPTS_PATH,
    TASK_CAPABILITY_MANIFEST_PATH,
    derived_firmware_semantic_profiles,
    derived_planning_backends,
    derived_promotion_receipts,
    derived_runtime_lane_aliases,
    derived_runtime_lanes,
    derived_task_manifest,
    load_runtime_authority,
    render_esp32_runtime_semantic_header,
    render_yaml_with_header,
)

HEADER = '# Generated from runtime_authority.yaml. Do not edit manually.'
CPP_HEADER = '// Generated from runtime_authority.yaml. Do not edit manually.'


def _write_if_changed(path: Path, content: str) -> bool:
    current = path.read_text(encoding='utf-8') if path.exists() else ''
    if current == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return True


def _render_outputs() -> dict[Path, str]:
    authority = load_runtime_authority()
    return {
        RUNTIME_PROFILES_PATH: render_yaml_with_header(derived_runtime_lanes(authority), header=HEADER),
        PLANNING_BACKEND_PROFILES_PATH: render_yaml_with_header(derived_planning_backends(authority), header=HEADER),
        RUNTIME_PROMOTION_RECEIPTS_PATH: render_yaml_with_header(derived_promotion_receipts(authority), header=HEADER),
        TASK_CAPABILITY_MANIFEST_PATH: render_yaml_with_header(derived_task_manifest(authority), header=HEADER),
        RUNTIME_LANE_ALIASES_PATH: render_yaml_with_header(derived_runtime_lane_aliases(authority), header=HEADER),
        FIRMWARE_SEMANTIC_PROFILES_PATH: render_yaml_with_header(derived_firmware_semantic_profiles(authority), header=HEADER),
        ESP32_FIRMWARE_PROFILE_HEADER_PATH: render_esp32_runtime_semantic_header(authority, header=CPP_HEADER),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail instead of writing when derived files are out of sync.')
    args = parser.parse_args()

    outputs = _render_outputs()
    drifted: list[str] = []
    for path, content in outputs.items():
        current = path.read_text(encoding='utf-8') if path.exists() else ''
        if current != content:
            drifted.append(path.name)
            if not args.check:
                _write_if_changed(path, content)
    if drifted and args.check:
        for item in drifted:
            print(f'[runtime-authority] drift detected: {item}')
        return 1
    if drifted:
        print('[runtime-authority] updated:', ', '.join(drifted))
    else:
        print('[runtime-authority] already in sync')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
