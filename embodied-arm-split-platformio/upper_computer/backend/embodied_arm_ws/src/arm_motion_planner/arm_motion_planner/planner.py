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
        """Normalize arbitrary target-like inputs into :class:`TargetSnapshot`.

        Args:
            target: Target snapshot, dictionary, or attribute-bearing object.

        Returns:
            TargetSnapshot: Normalized target snapshot.

        Raises:
            ValueError: If the target cannot be normalized.
        """
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
        """Validate a target before planning.

        Args:
            target: Normalized target snapshot.

        Returns:
            None.

        Raises:
            InvalidTargetError: If the target confidence or coordinates are invalid.
            WorkspaceViolationError: If the target is outside the configured XY workspace.
        """
        min_x, max_x, min_y, max_y = self.workspace
        if target.confidence < 0.5:
            raise InvalidTargetError('target confidence too low')
        if not all(isfinite(value) for value in (target.table_x, target.table_y, target.yaw, target.confidence)):
            raise InvalidTargetError('target pose contains non-finite values')
        if not (min_x <= target.table_x <= max_x and min_y <= target.table_y <= max_y):
            raise WorkspaceViolationError('target outside configured workspace')

    def _validate_place_pose(self, pose: dict[str, Any]) -> dict[str, float]:
        """Validate and normalize a place pose.

        Args:
            pose: Raw placement pose dictionary.

        Returns:
            dict[str, float]: Normalized placement pose.

        Raises:
            InvalidTargetError: If required fields are missing or non-finite.
            WorkspaceViolationError: If the pose is outside the configured workspace.
        """
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
        """Build a task-level pick-and-place stage plan.

        Args:
            context: Task context resolved by the orchestrator.
            target: Target snapshot selected for pickup.
            calibration: Active calibration profile.

        Returns:
            list[StagePlan]: Ordered stage plan for execution.

        Raises:
            InvalidTargetError: If target or calibration data is invalid.
            WorkspaceViolationError: If target or placement pose violates workspace bounds.
        """
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
            'graspCandidate': candidate,
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
        """Compile stage plans into runtime planning requests.

        Args:
            plan: Ordered stage plan.

        Returns:
            list[dict[str, Any]]: Serialized runtime planning requests.

        Raises:
            PlanningFailedError: If a non-gripper stage misses pose fields.
        """
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
                'graspCandidate': dict(payload.get('graspCandidate') or {}),
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
        """Compile and execute runtime planning requests via the MoveIt adapter.

        Args:
            plan: Ordered stage plan.

        Returns:
            list[PlanResult]: Planning results for non-gripper stages.
        """
        results: list[PlanResult] = []
        for request in self.compile_to_planning_requests(plan):
            if request['requestKind'] == 'gripper':
                continue
            if request['requestKind'] == 'named_pose':
                results.append(self._moveit_client.plan_named_pose(request['target']['named_pose'], metadata=request))
            else:
                results.append(self._moveit_client.plan_pose_goal(request['target'], frame=request['frame'], metadata=request))
        return results

    def summarize_plan(self, plan: list[StagePlan]) -> dict[str, Any]:
        """Return an HMI-friendly summary of a stage plan.

        Args:
            plan: Ordered stage plan.

        Returns:
            dict[str, Any]: Render-friendly plan summary.
        """
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
            'graspCandidateCount': len(first_candidate) and 1 or 0,
            'selectedCandidateId': first_candidate.get('candidate_id') or '',
        }

    def build_servo_command(self, axis: str, delta: float) -> CartesianJogCommand:
        """Build a validated Cartesian jog command.

        Args:
            axis: Servo axis in tool space.
            delta: Requested displacement in meters or radians.

        Returns:
            CartesianJogCommand: Validated servo command.

        Raises:
            ValueError: If axis or delta violate runtime bounds.
        """
        if axis not in SUPPORTED_SERVO_AXES:
            raise ValueError(f'unsupported servo axis: {axis}')
        if abs(delta) > MAX_SERVO_DELTA:
            raise ValueError('servo delta too large')
        return CartesianJogCommand(axis=axis, delta=float(delta))
