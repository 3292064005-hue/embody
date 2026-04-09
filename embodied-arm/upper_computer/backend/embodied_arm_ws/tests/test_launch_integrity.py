from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCH_DIR = ROOT / 'src' / 'arm_bringup' / 'launch'
ACTIVE_STACK_PACKAGES = {
    'arm_profiles',
    'arm_calibration',
    'arm_hardware_bridge',
    'arm_readiness_manager',
    'arm_safety_supervisor',
    'arm_camera_driver',
    'arm_perception',
    'arm_scene_manager',
    'arm_grasp_planner',
    'arm_description',
    'arm_moveit_config',
    'arm_motion_planner',
    'arm_motion_executor',
    'arm_task_orchestrator',
    'arm_diagnostics',
    'arm_logger',
    'arm_lifecycle_manager',
}
LEGACY_PACKAGES = {'arm_task_manager', 'arm_motion_bridge'}
OFFICIAL_RUNTIME = LAUNCH_DIR / 'official_runtime.launch.py'


def test_launch_files_compile():
    launch_files = sorted(LAUNCH_DIR.glob('*.py'))
    assert launch_files, 'expected bringup launch files'
    for path in launch_files:
        compile(path.read_text(encoding='utf-8'), str(path), 'exec')


def test_active_launch_files_reference_only_split_stack_packages():
    launch_files = sorted(LAUNCH_DIR.glob('*.py'))
    for path in launch_files:
        text = path.read_text(encoding='utf-8')
        for legacy in LEGACY_PACKAGES:
            assert legacy not in text, f'{path.name} should not reference deprecated package {legacy}'
        if 'launch_factory' not in text:
            for package in ACTIVE_STACK_PACKAGES:
                if package in text:
                    break
            else:
                raise AssertionError(f'{path.name} does not reference the active split stack')


def test_launch_files_reference_current_perception_chain():
    launch_files = sorted(LAUNCH_DIR.glob('*.py'))
    for path in launch_files:
        text = path.read_text(encoding='utf-8')
        assert 'arm_vision' not in text


def test_official_runtime_launch_exists():
    assert OFFICIAL_RUNTIME.exists(), 'official runtime launch missing'


def test_official_runtime_launch_is_compatibility_alias_to_runtime_sim():
    text = OFFICIAL_RUNTIME.read_text(encoding='utf-8')
    assert 'Compatibility alias' in text
    assert 'build_official_runtime_launch_description' in text
    assert 'official_runtime' in text
