from pathlib import Path

import yaml


def test_real_and_hybrid_launch_use_supported_camera_source_values():
    runtime_profiles = Path(__file__).resolve().parents[1] / 'src' / 'arm_bringup' / 'config' / 'runtime_profiles.yaml'
    payload = yaml.safe_load(runtime_profiles.read_text(encoding='utf-8')) or {}
    real_preview = payload.get('real_preview', {}) if isinstance(payload, dict) else {}
    hybrid_preview = payload.get('hybrid_preview', {}) if isinstance(payload, dict) else {}
    assert str(real_preview.get('camera_source', '')) == 'topic'
    assert str(hybrid_preview.get('camera_source', '')) == 'topic'


def test_runtime_lane_governance_is_loaded_from_runtime_authority() -> None:
    import yaml

    runtime_authority = Path(__file__).resolve().parents[1] / 'src' / 'arm_bringup' / 'config' / 'runtime_authority.yaml'
    payload = yaml.safe_load(runtime_authority.read_text(encoding='utf-8')) or {}
    governance = payload.get('runtime_governance', {}) if isinstance(payload, dict) else {}

    from arm_bringup.launch_factory import runtime_lane_governance_manifest

    manifest = runtime_lane_governance_manifest()
    assert tuple(governance.get('official_runtime_lanes', [])) == manifest['official_runtime_lanes']
    assert tuple(governance.get('experimental_runtime_lanes', [])) == manifest['experimental_runtime_lanes']
