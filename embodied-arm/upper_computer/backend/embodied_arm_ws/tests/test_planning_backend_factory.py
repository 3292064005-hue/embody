from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT / 'arm_motion_planner'))

from arm_motion_planner.backend_factory import DEFAULT_BACKEND_PROFILE_NAME, resolve_planning_backend
from arm_motion_planner.errors import PlanningFailedError, PlanningUnavailableError
from arm_motion_planner.moveit_client import MoveItClient


def test_validated_sim_profile_resolves_to_declared_runtime_backend() -> None:
    resolved = resolve_planning_backend(
        capability_mode='validated_sim',
        backend_name='validated_sim_runtime',
        backend_profile=DEFAULT_BACKEND_PROFILE_NAME,
    )
    assert resolved.declared is True
    assert resolved.profile_name == DEFAULT_BACKEND_PROFILE_NAME
    assert resolved.backend is not None


def test_validated_live_profile_remains_fail_closed_when_not_declared() -> None:
    resolved = resolve_planning_backend(
        capability_mode='validated_live',
        backend_name='validated_live_bridge',
        backend_profile='validated_live_bridge',
    )
    assert resolved.declared is False
    assert resolved.backend is None


def test_validated_sim_runtime_rejects_out_of_workspace_pose() -> None:
    client = MoveItClient(capability_mode='validated_sim', authoritative=True, backend_name='validated_sim_runtime')
    try:
        client.plan_pose_goal({'x': 0.8, 'y': 0.0, 'z': 0.2, 'yaw': 0.0}, frame='table')
    except PlanningFailedError as exc:
        assert 'workspace upper bound' in str(exc)
    else:  # pragma: no cover
        raise AssertionError('validated-sim backend must reject out-of-bounds requests')


def test_validated_live_runtime_stays_unavailable_without_bridge() -> None:
    client = MoveItClient(capability_mode='validated_live', authoritative=True, backend_name='validated_live_bridge')
    try:
        client.plan_named_pose('home')
    except PlanningUnavailableError as exc:
        assert 'validated_live requires an injected live planning backend' in str(exc)
    else:  # pragma: no cover
        raise AssertionError('validated-live backend must stay fail-closed by default')


def test_missing_backend_profile_file_fails_fast(monkeypatch, tmp_path: Path) -> None:
    from arm_motion_planner import backend_factory

    missing = tmp_path / 'missing_backends.yaml'
    monkeypatch.setenv('EMBODIED_ARM_PLANNING_BACKENDS_FILE', str(missing))
    try:
        backend_factory.load_backend_profiles()
    except RuntimeError as exc:
        assert 'planning backend profile file missing' in str(exc)
    else:  # pragma: no cover
        raise AssertionError('missing generated backend profile file must fail fast')
