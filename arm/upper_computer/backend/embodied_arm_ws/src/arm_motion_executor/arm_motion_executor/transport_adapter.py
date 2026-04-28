from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable

_FORWARDABLE_EXECUTION_MODES = frozenset({'authoritative_simulation', 'ros2_control_candidate', 'ros2_control_live'})
_REQUIRED_FORWARD_FIELDS = ('command_id', 'plan_id', 'task_id', 'stage', 'kind', 'timeout_sec')
_REQUIRED_EXECUTION_TARGET_FIELDS = ('joint_names', 'points')


@dataclass(frozen=True)
class TransportDispatchResult:
    """Immediate result of one motion-executor transport dispatch.

    Attributes:
        accepted: Whether the adapter accepted the dispatch request.
        forwarded: Whether the command was emitted onto an external transport.
        transport_mode: Stable transport-mode token for diagnostics.
        execution_mode: Runtime execution mode declared by the active lane.
        message: Human-readable dispatch summary.
    """

    accepted: bool
    forwarded: bool
    transport_mode: str
    execution_mode: str
    message: str


class CommandTransportAdapter:
    """Abstract command transport adapter for motion-executor dispatch.

    The adapter isolates controller shadow state from concrete transport.
    Authoritative lanes can reject commands when runtime mode and payload do not
    satisfy the declared forwarding contract.
    """

    def __init__(self, *, execution_mode: str) -> None:
        self._execution_mode = str(execution_mode or 'protocol_simulator').strip() or 'protocol_simulator'
        self._dispatch_count = 0
        self._last_command_id = ''
        self._last_message = ''

    @property
    def execution_mode(self) -> str:
        return self._execution_mode

    def dispatch(self, command: dict[str, Any]) -> TransportDispatchResult:
        raise NotImplementedError

    def requires_sequential_dispatch(self) -> bool:
        """Return whether the transport requires one-command-at-a-time dispatch.

        Returns:
            bool: ``True`` for transports that require terminal feedback before
            the next command can be submitted.
        """
        return False

    def snapshot(self) -> dict[str, Any]:
        return {
            'executionMode': self._execution_mode,
            'dispatchCount': int(self._dispatch_count),
            'lastCommandId': self._last_command_id,
            'lastMessage': self._last_message,
            'transportMode': self.transport_mode(),
            'authoritativeTransport': self._execution_mode in _FORWARDABLE_EXECUTION_MODES,
            'sequentialDispatch': self.requires_sequential_dispatch(),
        }

    def transport_mode(self) -> str:
        return self._execution_mode

    def _mark_dispatch(self, command_id: str, *, message: str = '') -> None:
        self._dispatch_count += 1
        self._last_command_id = str(command_id or '')
        self._last_message = str(message or '')

    @staticmethod
    def _validate_command_payload(command: dict[str, Any]) -> str | None:
        if not isinstance(command, dict):
            return 'command payload must be a dictionary'
        missing = [name for name in _REQUIRED_FORWARD_FIELDS if not str(command.get(name, '')).strip()]
        if missing:
            return f'missing required transport fields: {", ".join(missing)}'
        timeout_sec = float(command.get('timeout_sec', 0.0) or 0.0)
        if timeout_sec <= 0.0:
            return 'command timeout_sec must be positive for transport forwarding'
        return None

    @staticmethod
    def _validate_execution_target(target: Any) -> str | None:
        if not isinstance(target, dict):
            return 'execution_target must be a dictionary'
        missing = [name for name in _REQUIRED_EXECUTION_TARGET_FIELDS if not target.get(name)]
        if missing:
            return f'execution_target missing required fields: {", ".join(missing)}'
        joint_names = list(target.get('joint_names') or [])
        if not all(str(name).strip() for name in joint_names):
            return 'execution_target joint_names must be non-empty strings'
        points = list(target.get('points') or [])
        if not points:
            return 'execution_target points must contain at least one point'
        for index, point in enumerate(points, start=1):
            if not isinstance(point, dict):
                return f'execution_target point {index} must be a dictionary'
            positions = list(point.get('positions') or [])
            if len(positions) != len(joint_names):
                return f'execution_target point {index} positions must match joint_names length'
            time_from_start = float(point.get('time_from_start_sec', 0.0) or 0.0)
            if time_from_start <= 0.0:
                return f'execution_target point {index} time_from_start_sec must be positive'
        return None




@dataclass(frozen=True)
class ExecutionBackboneContract:
    """Normalized execution-backbone contract selected for one runtime lane.

    Attributes:
        execution_mode: Declared runtime execution mode token.
        transport_mode: Stable adapter/transport token exposed to diagnostics.
        authoritative_transport: Whether commands leave controller shadow state.
        sequential_dispatch: Whether the lane requires terminal feedback before
            dispatching the next command.
        rejection_message: Optional fail-closed reason when the declared lane
            cannot honor its execution contract.
    """

    execution_mode: str
    transport_mode: str
    authoritative_transport: bool
    sequential_dispatch: bool
    rejection_message: str = ''


def resolve_execution_backbone_contract(
    *,
    forward_hardware_commands: bool,
    execution_mode: str,
    ros2_control_available: bool,
) -> ExecutionBackboneContract:
    """Resolve the normalized execution-backbone contract for one lane.

    Args:
        forward_hardware_commands: Whether the active lane may emit hardware
            commands beyond shadow state.
        execution_mode: Runtime lane execution-mode token.
        ros2_control_available: Whether a ros2_control submission callback is
            available for validated-live candidate/live lanes.

    Returns:
        ExecutionBackboneContract: Stable contract consumed by adapter selection.

    Boundary behavior:
        Invalid authoritative declarations fail closed with a rejection contract
        instead of silently downgrading to preview/shadow dispatch.
    """
    mode = str(execution_mode or 'protocol_simulator').strip() or 'protocol_simulator'
    if not bool(forward_hardware_commands):
        if mode in _FORWARDABLE_EXECUTION_MODES:
            return ExecutionBackboneContract(
                execution_mode=mode,
                transport_mode='rejected',
                authoritative_transport=False,
                sequential_dispatch=False,
                rejection_message=f'{mode} requires forward_hardware_commands=true',
            )
        return ExecutionBackboneContract(
            execution_mode=mode,
            transport_mode='shadow_only',
            authoritative_transport=False,
            sequential_dispatch=False,
        )
    if mode == 'authoritative_simulation':
        return ExecutionBackboneContract(
            execution_mode=mode,
            transport_mode='ros_topic_dispatch',
            authoritative_transport=True,
            sequential_dispatch=False,
        )
    if mode in {'ros2_control_candidate', 'ros2_control_live'}:
        if not ros2_control_available:
            return ExecutionBackboneContract(
                execution_mode=mode,
                transport_mode='rejected',
                authoritative_transport=False,
                sequential_dispatch=False,
                rejection_message=f'{mode} requires a ros2_control submission callback',
            )
        return ExecutionBackboneContract(
            execution_mode=mode,
            transport_mode='ros2_control_trajectory',
            authoritative_transport=True,
            sequential_dispatch=True,
        )
    return ExecutionBackboneContract(
        execution_mode=mode,
        transport_mode='rejected',
        authoritative_transport=False,
        sequential_dispatch=False,
        rejection_message=f'unsupported forwarding execution mode: {mode}',
    )

class ShadowCommandTransportAdapter(CommandTransportAdapter):
    """Shadow-only adapter used by preview lanes.

    Commands are accepted into controller shadow state but are not forwarded to
    an external transport.
    """

    def dispatch(self, command: dict[str, Any]) -> TransportDispatchResult:
        command_id = str(command.get('command_id', '') or '')
        message = 'command retained in controller shadow state only'
        self._mark_dispatch(command_id, message=message)
        return TransportDispatchResult(True, False, 'shadow_only', self.execution_mode, message)

    def transport_mode(self) -> str:
        return 'shadow_only'


class RejectingCommandTransportAdapter(CommandTransportAdapter):
    """Adapter that fails closed when a lane declares an invalid transport contract."""

    def __init__(self, *, execution_mode: str, rejection_message: str) -> None:
        super().__init__(execution_mode=execution_mode)
        self._rejection_message = str(rejection_message)

    def dispatch(self, command: dict[str, Any]) -> TransportDispatchResult:
        command_id = str(command.get('command_id', '') or '')
        self._mark_dispatch(command_id, message=self._rejection_message)
        return TransportDispatchResult(False, False, 'rejected', self.execution_mode, self._rejection_message)

    def transport_mode(self) -> str:
        return 'rejected'


class RosTopicCommandTransportAdapter(CommandTransportAdapter):
    """ROS-topic transport adapter that forwards serialized hardware commands.

    The adapter validates command payloads before emitting them, ensuring that
    authoritative simulation lanes do not silently downgrade into malformed
    dispatcher dispatches.
    """

    def __init__(self, *, execution_mode: str, publish_json: Callable[[str], None]) -> None:
        super().__init__(execution_mode=execution_mode)
        self._publish_json = publish_json

    def dispatch(self, command: dict[str, Any]) -> TransportDispatchResult:
        validation_error = self._validate_command_payload(command)
        command_id = str(command.get('command_id', '') or '')
        if validation_error is not None:
            self._mark_dispatch(command_id, message=validation_error)
            return TransportDispatchResult(False, False, 'ros_topic_dispatch', self.execution_mode, validation_error)
        envelope = dict(command)
        envelope['execution_mode'] = self.execution_mode
        envelope['transport_contract'] = 'authoritative_execution_v1'
        envelope.setdefault('producer', 'motion_executor')
        envelope.setdefault('command_plane', 'task_execution')
        message = 'command forwarded to hardware dispatcher topic'
        self._mark_dispatch(command_id, message=message)
        self._publish_json(json.dumps(envelope, ensure_ascii=False))
        return TransportDispatchResult(True, True, 'ros_topic_dispatch', self.execution_mode, message)

    def transport_mode(self) -> str:
        return 'ros_topic_dispatch'


class Ros2ControlCommandTransportAdapter(CommandTransportAdapter):
    """ros2_control transport adapter for validated-live execution.

    Commands are converted into controller-friendly execution targets and
    submitted through the provided callback. The callback owns the actual ROS
    client interaction and terminal-result correlation.
    """

    def __init__(self, *, execution_mode: str, submit_command: Callable[[dict[str, Any]], tuple[bool, str] | dict[str, Any]]) -> None:
        super().__init__(execution_mode=execution_mode)
        self._submit_command = submit_command

    def requires_sequential_dispatch(self) -> bool:
        return True

    def dispatch(self, command: dict[str, Any]) -> TransportDispatchResult:
        validation_error = self._validate_command_payload(command)
        command_id = str(command.get('command_id', '') or '')
        if validation_error is not None:
            self._mark_dispatch(command_id, message=validation_error)
            return TransportDispatchResult(False, False, 'ros2_control_trajectory', self.execution_mode, validation_error)
        kind = str(command.get('kind', '') or '')
        if kind in {'EXEC_STAGE', 'HOME'}:
            target_error = self._validate_execution_target(command.get('execution_target'))
            if target_error is not None:
                self._mark_dispatch(command_id, message=target_error)
                return TransportDispatchResult(False, False, 'ros2_control_trajectory', self.execution_mode, target_error)
        try:
            response = self._submit_command(dict(command))
        except Exception as exc:  # pragma: no cover - runtime callback boundary
            message = f'ros2_control submission failed: {exc}'
            self._mark_dispatch(command_id, message=message)
            return TransportDispatchResult(False, False, 'ros2_control_trajectory', self.execution_mode, message)
        accepted = False
        message = 'command submitted to ros2_control controller'
        if isinstance(response, tuple):
            accepted = bool(response[0])
            if len(response) > 1 and str(response[1]).strip():
                message = str(response[1])
        elif isinstance(response, dict):
            accepted = bool(response.get('accepted', False))
            if str(response.get('message', '')).strip():
                message = str(response['message'])
        else:
            accepted = bool(response)
        self._mark_dispatch(command_id, message=message)
        return TransportDispatchResult(accepted, accepted, 'ros2_control_trajectory', self.execution_mode, message)

    def transport_mode(self) -> str:
        return 'ros2_control_trajectory'


def build_transport_adapter(
    *,
    forward_hardware_commands: bool,
    execution_mode: str,
    publish_json: Callable[[str], None],
    submit_ros2_control_command: Callable[[dict[str, Any]], tuple[bool, str] | dict[str, Any]] | None = None,
) -> CommandTransportAdapter:
    """Build the concrete command transport adapter for the active runtime lane.

    Args:
        forward_hardware_commands: Whether the active runtime lane is allowed to
            emit hardware commands beyond shadow-state dispatch.
        execution_mode: Runtime execution mode declared by launch/runtime config.
        publish_json: Callback used to publish serialized command payloads for
            dispatcher-backed transports.
        submit_ros2_control_command: Optional callback used by ros2_control candidate/live
            execution lanes to submit controller commands.

    Returns:
        CommandTransportAdapter: Concrete adapter instance.

    Boundary behavior:
        Authoritative execution modes fail closed when hardware forwarding is
        disabled or when the mode token is unsupported. Preview modes stay
        shadow-only by design.
    """
    contract = resolve_execution_backbone_contract(
        forward_hardware_commands=forward_hardware_commands,
        execution_mode=execution_mode,
        ros2_control_available=submit_ros2_control_command is not None,
    )
    if contract.transport_mode == 'shadow_only':
        return ShadowCommandTransportAdapter(execution_mode=contract.execution_mode)
    if contract.transport_mode == 'ros_topic_dispatch':
        return RosTopicCommandTransportAdapter(execution_mode=contract.execution_mode, publish_json=publish_json)
    if contract.transport_mode == 'ros2_control_trajectory' and submit_ros2_control_command is not None:
        return Ros2ControlCommandTransportAdapter(execution_mode=contract.execution_mode, submit_command=submit_ros2_control_command)
    return RejectingCommandTransportAdapter(execution_mode=contract.execution_mode, rejection_message=contract.rejection_message or 'execution backbone contract rejected')
