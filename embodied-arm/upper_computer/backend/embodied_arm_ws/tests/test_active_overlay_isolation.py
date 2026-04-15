from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.materialize_active_ros_overlay import active_workspace_packages


def test_active_overlay_dependency_closure_excludes_compatibility_and_experimental_packages() -> None:
    roots, closure = active_workspace_packages()
    closure_set = set(closure)
    assert 'arm_task_manager' not in closure_set
    assert 'arm_motion_bridge' not in closure_set
    assert 'arm_vision' not in closure_set
    assert 'arm_hmi' not in closure_set
    assert set(roots).issubset(closure_set)


def test_active_overlay_dependency_closure_keeps_required_runtime_dependencies() -> None:
    _, closure = active_workspace_packages()
    closure_set = set(closure)
    for package in ('arm_backend_common', 'arm_common', 'arm_interfaces', 'arm_description', 'arm_control_bringup', 'arm_moveit_config'):
        assert package in closure_set
