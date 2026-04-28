# demo stack: runtime core (including arm_scene_manager arm_grasp_planner) + optional demo assets
from arm_bringup.launch_factory import build_launch_description


def generate_launch_description():
    return build_launch_description('full_demo', include_mock_targets=True)