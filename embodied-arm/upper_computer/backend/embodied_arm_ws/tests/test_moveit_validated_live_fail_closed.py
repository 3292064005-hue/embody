from arm_motion_planner.moveit_client import MoveItClient, PlanResult, PlanningRequest
from arm_motion_planner.errors import PlanningUnavailableError


def test_validated_live_requires_injected_backend() -> None:
    client = MoveItClient(capability_mode='validated_live', authoritative=True, backend_name='validated_live_bridge')
    try:
        client.plan_named_pose('home')
    except PlanningUnavailableError as exc:
        assert 'validated_live requires an injected live planning backend' in str(exc)
    else:  # pragma: no cover - safety assertion
        raise AssertionError('validated_live lane must fail closed without injected backend')


def test_validated_live_accepts_injected_backend() -> None:
    def backend(request: PlanningRequest) -> PlanResult:
        return PlanResult(
            accepted=True,
            success=True,
            planner_plugin='pilz',
            scene_source='live_scene',
            request_kind=request.request_kind,
            trajectory={'waypoints': [dict(request.target)], 'executionModel': 'validated_live_bridge'},
            planning_time_sec=0.02,
            request=request,
            authoritative=True,
            capability_mode='validated_live',
            backend_name='validated_live_bridge',
        )

    client = MoveItClient(capability_mode='validated_live', authoritative=True, backend_name='validated_live_bridge', planning_backend=backend)
    result = client.plan_named_pose('home')
    assert result.success is True
    assert result.authoritative is True
    assert result.capability_mode == 'validated_live'
