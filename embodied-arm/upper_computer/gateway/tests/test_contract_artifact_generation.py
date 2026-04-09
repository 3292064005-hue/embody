from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_generated_contract_artifacts_are_in_sync() -> None:
    sync_result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'sync_runtime_authority.py'), '--check'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert sync_result.returncode == 0, sync_result.stdout + sync_result.stderr
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'generate_contract_artifacts.py'), '--check'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_contract_manifest_contains_authoritative_fields() -> None:
    manifest = json.loads((ROOT / 'docs' / 'generated' / 'runtime_contract_manifest.json').read_text(encoding='utf-8'))
    assert manifest['readiness']['publicFields'][:3] == ['runtimeHealthy', 'modeReady', 'allReady']
    assert manifest['readiness']['commandRequiredByName']['recover'] == ['ros2', 'task_orchestrator', 'hardware_bridge']
    assert 'sourceStm32Authoritative' in manifest['hardware']['authorityFields']
    assert manifest['ros2']['topics']['cameraHealthSummary'] == '/arm/camera/health'
    assert manifest['ros2']['services']['calibrationManagerReload'] == '/calibration_manager_node/reload'
    assert manifest['ros2']['actions']['pickPlaceTask'] == '/arm/pick_place_task'
    assert manifest['runtime']['laneAliases']['official_runtime'] == 'sim_preview'
    assert manifest['runtime']['promotionReceipts']['validated_live']['promoted'] is False
    assert manifest['runtime']['promotionReceipts']['validated_live']['effective'] is False
    assert manifest['runtime']['promotionReceipts']['validated_sim']['promoted'] is True
    assert manifest['runtime']['promotionReceipts']['validated_sim']['effective'] is True
