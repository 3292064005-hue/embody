from __future__ import annotations

import json

from scripts.generate_contract_artifacts import render_outputs as render_contract_outputs
from scripts.sync_doc_compatibility_mirrors import MANIFEST_PATH, render_outputs


def test_doc_compatibility_mirrors_are_generated_and_declared() -> None:
    outputs = render_outputs()
    manifest = json.loads(outputs[MANIFEST_PATH])
    entries = {item['legacyPath']: item for item in manifest['entries']}
    assert entries['docs/FIRMWARE_SPLIT_INTEGRATION.md']['canonicalPath'] == 'docs/operations/firmware-integration.md'
    assert entries['docs/FIRMWARE_SPLIT_INTEGRATION.md']['generator'] == 'upper_computer/scripts/sync_doc_compatibility_mirrors.py'
    assert entries['docs/SERIAL_PROTOCOL.md']['canonicalPath'] == 'docs/interfaces/stm32-serial-protocol.md'
    assert entries['docs/SERIAL_PROTOCOL.md']['generator'] == 'upper_computer/scripts/sync_doc_compatibility_mirrors.py'
    assert entries['docs/FRONTEND_VALIDATION_STATUS.md']['canonicalPath'] == 'docs/evidence/frontend-validation-status.md'
    assert entries['docs/FRONTEND_VALIDATION_STATUS.md']['generator'] == 'upper_computer/scripts/sync_doc_compatibility_mirrors.py'
    assert entries['docs/CONTRACT_INDEX.md']['canonicalPath'] == 'docs/interfaces/api-contract.md'
    assert entries['docs/CONTRACT_INDEX.md']['generator'] == 'upper_computer/scripts/generate_contract_artifacts.py'
    assert entries['docs/ROS2_INTERFACE_INDEX.md']['canonicalPath'] == 'docs/interfaces/ros2-interface-index.md'
    assert entries['docs/ROS2_INTERFACE_INDEX.md']['generator'] == 'upper_computer/scripts/generate_contract_artifacts.py'


def test_contract_and_ros2_mirrors_match_generated_contract_outputs() -> None:
    contract_outputs = render_contract_outputs()
    contract_doc = next(content for path, content in contract_outputs.items() if path.name == 'CONTRACT_INDEX.md')
    ros2_doc = next(content for path, content in contract_outputs.items() if path.name == 'ROS2_INTERFACE_INDEX.md')
    assert 'generated compatibility mirror' in contract_doc
    assert 'generated/runtime_contract_summary.md' in contract_doc
    assert 'docs/interfaces/api-contract.md' in contract_doc
    assert 'generated compatibility mirror' in ros2_doc
    assert '/arm/camera/health' in ros2_doc
    assert '/arm/camera/image_raw' in ros2_doc
    assert '/calibration_manager_node/reload' in ros2_doc


def test_serial_and_firmware_mirrors_keep_machine_readable_tokens() -> None:
    outputs = render_outputs()
    firmware_doc = outputs[next(path for path in outputs if path.name == 'FIRMWARE_SPLIT_INTEGRATION.md')]
    serial_doc = outputs[next(path for path in outputs if path.name == 'SERIAL_PROTOCOL.md')]
    assert 'generated compatibility mirror' in firmware_doc
    assert '/stream' in firmware_doc
    assert '/voice/events' in firmware_doc
    assert 'generated compatibility mirror' in serial_doc
    assert 'Sequence: `uint8`' in serial_doc
    assert '旧文档中出现过 `ESTOP / SAFE_HALT / JOG / GRIPPER`' in serial_doc
