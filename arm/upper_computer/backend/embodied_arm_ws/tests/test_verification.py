from arm_backend_common.data_models import HardwareSnapshot, TargetSnapshot, TaskContext, TaskProfile
from arm_task_orchestrator.verification import VerificationManager


def test_verification_target_still_visible_fails():
    manager = VerificationManager()
    task = TaskContext(task_id='1', selected_target=TargetSnapshot(target_id='t1', received_monotonic=0.0), verify_deadline=0.0)
    profile = TaskProfile(stale_target_sec=1.0, verify_strategy='hardware_or_target_lost')
    hardware = HardwareSnapshot(stm32_online=True, updated_monotonic=0.0)
    latest = TargetSnapshot(target_id='t1', received_monotonic=0.2)
    result = manager.verify(task, profile, hardware, latest_target=latest, now=0.5)
    assert result.finished
    assert not result.success


def test_verification_accepts_target_pose_change_strategy():
    manager = VerificationManager()
    task = TaskContext(task_id='1', selected_target=TargetSnapshot(target_id='t1', table_x=0.1, table_y=0.1, yaw=0.0), verify_deadline=0.0)
    profile = TaskProfile(stale_target_sec=1.0, verify_strategy='target_pose_changed')
    hardware = HardwareSnapshot(stm32_online=True, updated_monotonic=0.0)
    latest = TargetSnapshot(target_id='t1', table_x=0.2, table_y=0.1, yaw=0.0, received_monotonic=0.2)
    result = manager.verify(task, profile, hardware, latest_target=latest, now=0.5)
    assert result.finished
    assert result.success
