from arm_backend_common.data_models import HardwareSnapshot, TargetSnapshot, TaskContext, TaskProfile
from arm_task_manager.verification import VerificationManager


def test_verification_target_still_visible_fails():
    manager = VerificationManager()
    task = TaskContext(task_id='1', selected_target=TargetSnapshot(target_id='t1', received_monotonic=0.0), verify_deadline=0.0)
    profile = TaskProfile(stale_target_sec=1.0, verify_strategy='hardware_or_target_lost')
    hardware = HardwareSnapshot(stm32_online=True, updated_monotonic=0.0)
    latest = TargetSnapshot(target_id='t1', received_monotonic=0.2)
    result = manager.verify(task, profile, hardware, latest_target=latest, now=0.5)
    assert result.finished
    assert not result.success
