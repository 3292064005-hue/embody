from arm_backend_common.data_models import TargetSnapshot


def test_target_freshness():
    target = TargetSnapshot(received_monotonic=10.0)
    assert target.is_fresh(1.0, now=10.5)
    assert not target.is_fresh(1.0, now=11.2)
