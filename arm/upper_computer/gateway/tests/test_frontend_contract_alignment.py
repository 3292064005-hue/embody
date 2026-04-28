from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_frontend_clear_targets_uses_post_contract() -> None:
    source = (ROOT / 'frontend' / 'src' / 'services' / 'api' / 'vision.ts').read_text(encoding='utf-8')
    assert "postVoid('/api/vision/clear-targets')" in source
    assert "putVoid('/api/vision/clear-targets')" not in source


def test_voice_events_are_mirrored_to_log_and_audit_streams() -> None:
    source = (ROOT / 'gateway' / 'ros_bridge.py').read_text(encoding='utf-8')
    assert "('log.event.created', stored)" in source
    assert "('audit.event.created', audit)" in source


def test_voice_events_are_marked_observability_only() -> None:
    source = (ROOT / 'gateway' / 'ros_bridge.py').read_text(encoding='utf-8')
    assert "'telemetryOnly': bool(payload.get('telemetryOnly', True))" in source
    assert "'routing': str(payload.get('routing', 'observability_only') or 'observability_only')" in source
