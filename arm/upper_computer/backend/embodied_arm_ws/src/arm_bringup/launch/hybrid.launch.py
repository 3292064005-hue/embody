# active split stack: arm_profiles arm_calibration arm_hardware_bridge arm_readiness_manager arm_safety_supervisor arm_motion_planner arm_motion_executor arm_task_orchestrator arm_diagnostics arm_logger
from arm_bringup.launch_factory import build_launch_description


def generate_launch_description():
    return build_launch_description('hybrid')
