from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = json.loads((ROOT / 'docs' / 'generated' / 'runtime_contract_manifest.json').read_text(encoding='utf-8'))
INDEX = (ROOT / 'docs' / 'ROS2_INTERFACE_INDEX.md').read_text(encoding='utf-8')


def test_contract_manifest_contains_authoritative_service_and_action_names() -> None:
    services = MANIFEST['ros2']['services']
    actions = MANIFEST['ros2']['actions']
    assert services['calibrationManagerReload'] == '/calibration_manager_node/reload'
    assert services['activateCalibration'] == '/arm/activate_calibration'
    assert actions['pickPlaceTask'] == '/arm/pick_place_task'
    assert actions['manualServo'] == '/arm/manual_servo'


def test_generated_interface_index_matches_authoritative_names() -> None:
    assert '/arm/camera/health' in INDEX
    assert '/arm/camera/health_summary' not in INDEX
    assert '/calibration_manager_node/reload' in INDEX
    assert '/arm/reload_calibration' not in INDEX
