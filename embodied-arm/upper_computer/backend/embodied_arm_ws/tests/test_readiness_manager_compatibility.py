from arm_readiness_manager.readiness import ReadinessManager


def test_snapshot_accepts_legacy_mode_override_without_mutating_manager_mode() -> None:
    manager = ReadinessManager()
    manager.set_mode('manual')
    snapshot = manager.snapshot('idle')
    assert snapshot.mode == 'idle'
    assert manager.snapshot().mode == 'manual'
