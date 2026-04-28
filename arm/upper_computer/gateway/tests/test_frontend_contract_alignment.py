from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_frontend_clear_targets_uses_post_contract() -> None:
    vision_service = (ROOT / 'frontend' / 'src' / 'services' / 'api' / 'vision.ts').read_text(encoding='utf-8')
    generated_client = (ROOT / 'frontend' / 'src' / 'api' / 'generated' / 'index.ts').read_text(encoding='utf-8')
    assert 'clearVisionTargetSet' in vision_service
    assert 'await clearVisionTargetSet();' in vision_service
    assert "visionClearTargets: '/api/vision/clear-targets'" in generated_client
    assert 'await postEnvelope<null>(routes.visionClearTargets);' in generated_client
    assert 'putEnvelope<null>(routes.visionClearTargets)' not in generated_client


def test_voice_events_are_mirrored_to_log_and_audit_streams() -> None:
    source = (ROOT / 'gateway' / 'ros_bridge.py').read_text(encoding='utf-8')
    assert "('log.event.created', stored)" in source
    assert "('audit.event.created', audit)" in source


def test_voice_events_are_marked_observability_only() -> None:
    source = (ROOT / 'gateway' / 'ros_bridge.py').read_text(encoding='utf-8')
    assert "'telemetryOnly': bool(payload.get('telemetryOnly', True))" in source
    assert "'routing': str(payload.get('routing', 'observability_only') or 'observability_only')" in source
