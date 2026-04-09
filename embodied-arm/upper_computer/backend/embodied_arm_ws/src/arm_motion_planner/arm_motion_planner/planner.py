from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from arm_backend_common.data_models import CalibrationProfile, TargetSnapshot, TaskContext
from arm_backend_common.stage_plan import StagePlan

from .errors import InvalidTargetError, PlanningFailedError, WorkspaceViolationError
from .moveit_client import MoveItClient, PlanResult
from .providers import GraspPlanProvider, GraspPlannerAdapter, SceneManagerAdapter, SceneSnapshotProvider

POSE_KEYS = ('x', 'y', 'z', 'yaw')
SUPPORTED_SERVO_AXES = frozenset({'x', 'y', 'z', 'rx', 'ry', 'rz'})
MAX_SERVO_DELTA = 0.1


@dataclass
class CartesianJogCommand:
    """Command describing a single Cartesian jog step."""

    axis: str
    delta: float
    frame: str = 'tool0'


class MotionPlanner:
    """Task-level motion planner that compiles task intent into runtime requests."""

    def __init__(
        self,
        workspace: tuple[float, float, float, float] = (-0.35, 0.35, -0.35, 0.35),
        *,
        moveit_client: MoveItClient | None = None,
        scene_manager: SceneSnapshotProvider | None = None,
        grasp_planner: GraspPlanProvider | None = None,
    ) -> None:
        """Initialize the motion planner.

        Args:
            workspace: Planner XY workspace bounds.
            moveit_client: Runtime planning adapter.
            scene_manager: Optional scene-snapshot provider.
            grasp_planner: Optional grasp-plan provider.

        Returns:
            None.

        Raises:
            ValueError: If the workspace bounds are invalid.
        """
        if len(workspace) != 4 or not all(isfinite(float(value)) for value in workspace):
            raise ValueError('workspace must contain four finite bounds')
        self.workspace = tuple(float(value) for value in workspace)
        self._moveit_client = moveit_client or MoveItClient()
        self._scene_manager = scene_manager or SceneManagerAdapter()
        self._grasp_planner = grasp_planner or GraspPlannerAdapter()

    def _normalize_target_snapshot(self, target: TargetSnapshot | dict[str, Any] | Any) -> TargetSnapshot:
        """Normalize arbitrary target-like inputs into :class:`TargetSnapshot`."""
        if isinstance(target, TargetSnapshot):
            return target
        if isinstance(target, dict):
            payload = dict(target)
        elif hasattr(target, 'target_id') or hasattr(target, 'table_x'):
            payload = {
                'target_id': getattr(target, 'target_id', ''),
                'target_type': getattr(target, 'target_type', getattr(target, 'type', 'unknown')),
                'semantic_label': getattr(target, 'semantic_label', getattr(target, 'label', getattr(target, 'target_type', 'unknown'))),
                'table_x': getattr(target, 'table_x', getattr(target, 'x', 0.0)),
                'table_y': getattr(target, 'table_y', getattr(target, 'y', 0.0)),
                'yaw': getattr(target, 'yaw', 0.0),
                'confidence': getattr(target, 'confidence', 0.0),
            }
        else:
            raise ValueError('target must be a TargetSnapshot, dictionary, or target-like object')
        return TargetSnapshot(
            target_id=str(payload.get('target_id', '')),
            target_type=str(payload.get('target_type', payload.get('type', 'unknown'))),
            semantic_label=str(payload.get('semantic_label', payload.get('label', payload.get('target_type', 'unknown')))),
            table_x=float(payload.get('table_x', payload.get('x', 0.0))),
            table_y=float(payload.get('table_y', payload.get('y', 0.0))),
            yaw=float(payload.get('yaw', 0.0)),
            confidence=float(payload.get('confidence', 0.0)),
        )

    def _validate_target(self, target: TargetSnapshot) -> None:
        """Validate a target before planning."""
        min_x, max_x, min_y, max_y = self.workspace
        if target.confidence < 0.5:
            raise InvalidTargetError('target confidence too low')
        if not all(isfinite(value) for value in (target.table_x, target.table_y, target.yaw, target.confidence)):
            raise InvalidTargetError('target pose contains non-finite values')
        if not (min_x <= target.table_x <= max_x and min_y <= target.table_y <= max_y):
            raise WorkspaceViolationError('target outside configured workspace')

    def _validate_place_pose(self, pose: dict[str, Any]) -> dict[str, float]:
        """Validate and normalize a place pose."""
        required = {'x', 'y', 'yaw'}
        missing = required.difference(pose)
        if missing:
            raise InvalidTargetError(f'place pose missing fields: {sorted(missing)}')
        normalized = {key: float(pose[key]) for key in required}
        if not all(isfinite(value) for value in normalized.values()):
            raise InvalidTargetError('place pose contains non-finite values')
        min_x, max_x, min_y, max_y = self.workspace
        if not (min_x <= normalized['x'] <= max_x and min_y <= normalized['y'] <= max_y):
            raise WorkspaceViolationError('place pose outside configured workspace')
        return normalized

    def build_pick_place_plan(self, context: TaskContext, target: TargetSnapshot, calibration: CalibrationProfile) -> list[StagePlan]:
        """Build a task-level pick-and-place stage plan."""
        target_snapshot = self._normalize_target_snapshot(target)
        self._validate_target(target_snapshot)
        place_pose = self._validate_place_pose(context.active_place_pose or calibration.resolve_place_profile(context.place_profile))
        if not (calibration.pre_grasp_z > calibration.grasp_z and calibration.retreat_z >= calibration.pre_grasp_z):
            raise InvalidTargetError('invalid calibration z ordering')
        grasp_plan = self._grasp_planner.plan(target_snapshot.to_dict(), {**place_pose, 'z': calibration.place_z})
        candidate = dict(grasp_plan.get('candidate') or {})
        grasp_x = float(candidate.get('grasp_x', target_snapshot.table_x))
        grasp_y = float(candidate.get('grasp_y', target_snapshot.table_y))
        grasp_yaw = float(candidate.get('yaw', target_snapshot.yaw))
        grasp_x, grasp_y, grasp_yaw = calibration.apply_target(grasp_x, grasp_y, grasp_yaw)
        scene_snapshot = self._scene_manager.sync_scene({'target': target_snapshot.to_dict()})
        common = {
            'frame': 'table',
            'taskId': context.task_id,
            'targetId': target_snapshot.target_id,
            'sceneSnapshot': scene_snapshot,
            'sceneSnapshotId': str(scene_snapshot.get('snapshotId', '')),
            'sceneProviderMode': str(scene_snapshot.get('providerMode', getattr(self._scene_manager, 'provider_mode', 'unknown'))),
            'sceneProviderAuthoritative': bool(scene_snapshot.get('providerAuthoritative', getattr(self._scene_manager, 'authoritative', False))),
            'graspCandidate': candidate,
            'graspCandidateBatchId': str(grasp_plan.get('candidateBatchId', '')),
            'graspProviderMode': str(grasp_plan.get('providerMode', getattr(self._grasp_planner, 'provider_mode', 'unknown'))),
            'graspProviderAuthoritative': bool(grasp_plan.get('providerAuthoritative', getattr(self._grasp_planner, 'authoritative', False))),
        }
        return [
            StagePlan('move_to_pregrasp', 'connector', {'x': grasp_x, 'y': grasp_y, 'z': calibration.pre_grasp_z, 'yaw': grasp_yaw, 'timeoutSec': 1.0, **common}),
            StagePlan('descend', 'propagator', {'x': grasp_x, 'y': grasp_y, 'z': calibration.grasp_z, 'yaw': grasp_yaw, 'timeoutSec': 0.8, **common}),
            StagePlan('close_gripper', 'gripper', {'open': False, 'timeoutSec': 0.6, **common}),
            StagePlan('lift', 'propagator', {'x': grasp_x, 'y': grasp_y, 'z': calibration.retreat_z, 'yaw': grasp_yaw, 'timeoutSec': 0.8, **common}),
            StagePlan('move_to_place', 'connector', {**place_pose, 'z': calibration.place_z, 'timeoutSec': 1.0, **common}),
            StagePlan('open_gripper', 'gripper', {'open': True, 'timeoutSec': 0.6, **common}),
            StagePlan('retreat', 'propagator', {'x': place_pose['x'], 'y': place_pose['y'], 'z': calibration.retreat_z, 'yaw': place_pose['yaw'], 'timeoutSec': 0.8, **common}),
            StagePlan('go_home', 'connector', {'named_pose': 'home', 'timeoutSec': 1.0, **common}),
        ]

    def compile_to_planning_requests(self, plan: list[StagePlan]) -> list[dict[str, Any]]:
        """Compile stage plans into runtime planning requests."""
        requests: list[dict[str, Any]] = []
        for sequence, stage in enumerate(plan, start=1):
            payload = dict(stage.payload)
            request: dict[str, Any] = {
                'sequence': sequence,
                'stageName': stage.name,
                'stageKind': stage.kind,
                'frame': str(payload.get('frame', 'table')),
                'timeoutSec': float(payload.get('timeoutSec', 1.0)),
                'taskId': str(payload.get('taskId', '')),
                'targetId': str(payload.get('targetId', '')),
                'sceneSnapshot': dict(payload.get('sceneSnapshot') or {}),
                'sceneSnapshotId': str(payload.get('sceneSnapshotId', '')),
                'sceneProviderMode': str(payload.get('sceneProviderMode', 'unknown')),
                'sceneProviderAuthoritative': bool(payload.get('sceneProviderAuthoritative', False)),
                'graspCandidate': dict(payload.get('graspCandidate') or {}),
                'graspCandidateBatchId': str(payload.get('graspCandidateBatchId', '')),
                'graspProviderMode': str(payload.get('graspProviderMode', 'unknown')),
                'graspProviderAuthoritative': bool(payload.get('graspProviderAuthoritative', False)),
            }
            if 'named_pose' in payload:
                request['requestKind'] = 'named_pose'
                request['target'] = {'named_pose': str(payload['named_pose'])}
            elif stage.kind == 'gripper':
                request['requestKind'] = 'gripper'
                request['target'] = {'open': bool(payload.get('open', False))}
            else:
                missing = [key for key in POSE_KEYS if key not in payload]
                if missing:
                    raise PlanningFailedError(f'{stage.name} missing pose payload fields: {missing}')
                request['requestKind'] = 'pose_goal'
                request['target'] = {key: float(payload[key]) for key in POSE_KEYS}
            requests.append(request)
        return requests

    def runtime_plan_results(self, plan: list[StagePlan]) -> list[PlanResult]:
        """Compile and execute runtime planning requests via the MoveIt adapter."""
        results: list[PlanResult] = []
        for request in self.compile_to_planning_requests(plan):
            if request['requestKind'] == 'gripper':
                continue
            if request['requestKind'] == 'named_pose':
                results.append(self._moveit_client.plan_named_pose(request['target']['named_pose'], metadata=request))
            else:
                results.append(self._moveit_client.plan_pose_goal(request['target'], frame=request['frame'], metadata=request))
        return results

    @staticmethod
    def _trajectory_waypoint_joint_points(trajectory: dict[str, Any]) -> dict[str, Any] | None:
        waypoints = list(trajectory.get('waypoints') or [])
        joint_waypoints = [item for item in waypoints if isinstance(item, dict) and isinstance(item.get('joints'), dict)]
        if not joint_waypoints:
            return None
        ordered_joint_names = list(dict(joint_waypoints[-1].get('joints', {})).keys())
        if not ordered_joint_names:
            return None
        points = []
        for index, waypoint in enumerate(joint_waypoints, start=1):
            joints = dict(waypoint.get('joints') or {})
            points.append({
                'positions': [float(joints[name]) for name in ordered_joint_names],
                'time_from_start_sec': round(0.35 * index, 3),
            })
        return {
            'controller': 'arm',
            'joint_names': ordered_joint_names,
            'points': points,
        }

    def _plan_result_to_execution_target(self, result: PlanResult) -> dict[str, Any] | None:
        trajectory = dict(result.trajectory or {})
        controller_targets = trajectory.get('controllerTargets')
        if isinstance(controller_targets, dict):
            arm_target = controller_targets.get('arm') if isinstance(controller_targets.get('arm'), dict) else controller_targets
            if isinstance(arm_target, dict) and arm_target.get('joint_names') and arm_target.get('points'):
                return dict(arm_target)
        return self._trajectory_waypoint_joint_points(trajectory)

    def attach_runtime_execution_targets(self, plan: list[StagePlan]) -> list[StagePlan]:
        requests = self.compile_to_planning_requests(plan)
        planning_results = self.runtime_plan_results(plan)
        result_index = 0
        enriched: list[StagePlan] = []
        for stage, request in zip(plan, requests):
            payload = dict(stage.payload)
            if request['requestKind'] == 'gripper':
                enriched.append(StagePlan(stage.name, stage.kind, payload))
                continue
            if result_index >= len(planning_results):
                raise PlanningFailedError('runtime planning results out of sync with stage requests')
            result = planning_results[result_index]
            result_index += 1
            if not result.accepted or not result.success:
                raise PlanningFailedError(result.error_message or f'runtime planning failed for stage {stage.name}')
            payload['planningTrajectory'] = dict(result.trajectory or {})
            execution_target = self._plan_result_to_execution_target(result)
            if execution_target is not None:
                payload['executionTarget'] = execution_target
            enriched.append(StagePlan(stage.name, stage.kind, payload))
        return enriched

    def summarize_plan(self, plan: list[StagePlan]) -> dict[str, Any]:
        """Return an HMI-friendly summary of a stage plan."""
        stage_timeouts = [float(stage.payload.get('timeoutSec', 0.0)) for stage in plan]
        first_scene = next((dict(stage.payload.get('sceneSnapshot') or {}) for stage in plan if stage.payload.get('sceneSnapshot')), {})
        first_candidate = next((dict(stage.payload.get('graspCandidate') or {}) for stage in plan if stage.payload.get('graspCandidate')), {})
        return {
            'stageNames': [stage.name for stage in plan],
            'stageCount': len(plan),
            'containsGripperStage': any(stage.kind == 'gripper' for stage in plan),
            'totalTimeoutSec': round(sum(stage_timeouts), 3),
            'placeTarget': next((stage.payload.get('targetId') for stage in plan if stage.name == 'move_to_place'), None),
            'sceneObjectCount': int(first_scene.get('objectCount', 0)),
            'attachmentCount': len(first_scene.get('attachments') or []),
            'sceneSnapshotId': str(first_scene.get('snapshotId', '')),
            'sceneProviderMode': str(first_scene.get('providerMode', 'unknown')),
            'graspCandidateCount': len(first_candidate) and 1 or 0,
            'selectedCandidateId': first_candidate.get('candidate_id') or '',
        }

    def build_servo_command(self, axis: str, delta: float) -> CartesianJogCommand:
        """Build a validated Cartesian jog command."""
        if axis not in SUPPORTED_SERVO_AXES:
            raise ValueError(f'unsupported servo axis: {axis}')
        if abs(delta) > MAX_SERVO_DELTA:
            raise ValueError('servo delta too large')
        return CartesianJogCommand(axis=axis, delta=float(delta))
