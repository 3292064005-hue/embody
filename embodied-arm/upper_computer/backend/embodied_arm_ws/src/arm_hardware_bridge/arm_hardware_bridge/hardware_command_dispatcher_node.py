from __future__ import annotations

import json
import time
from typing import Any, Dict

try:
    import rclpy
    from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
    from std_msgs.msg import String
    from arm_common import TopicNames
except Exception:  # pragma: no cover
    rclpy = None
    ManagedLifecycleNode = object

    def lifecycle_main(factory, args=None):
        del factory, args
        raise RuntimeError('rclpy unavailable')

    class String:  # type: ignore[override]
        def __init__(self, data: str = '') -> None:
            self.data = data

    _ARM_PREFIX = '/' + 'arm'

    class TopicNames:
        HARDWARE_STM32_TX = _ARM_PREFIX + '/hardware/stm32_tx'
        HARDWARE_FEEDBACK = _ARM_PREFIX + '/hardware/feedback'
        HARDWARE_DISPATCHER_STATE = _ARM_PREFIX + '/hardware/dispatcher_state'
        HARDWARE_COMMAND = _ARM_PREFIX + '/hardware/command'
        INTERNAL_HARDWARE_CMD = _ARM_PREFIX + '/internal/hardware_cmd'
        HARDWARE_STM32_RX = _ARM_PREFIX + '/hardware/stm32_rx'

from arm_backend_common.enums import HardwareCommand
from arm_backend_common.safety_limits import SafetyLimits, SafetyViolation, load_safety_limits
from arm_backend_common.protocol import build_frame, decode_hex_frame, decode_payload
from .feedback_tracker import PendingCommand

CMD_MAP = {
    'HOME': HardwareCommand.HOME,
    'STOP': HardwareCommand.STOP,
    'SAFE_HALT': HardwareCommand.STOP,
    'ESTOP': HardwareCommand.STOP,
    'EXEC_STAGE': HardwareCommand.EXEC_STAGE,
    'RESET_FAULT': HardwareCommand.RESET_FAULT,
    'OPEN_GRIPPER': HardwareCommand.OPEN_GRIPPER,
    'CLOSE_GRIPPER': HardwareCommand.CLOSE_GRIPPER,
    'QUERY_STATE': HardwareCommand.QUERY_STATE,
    'SET_JOINTS': HardwareCommand.SET_JOINTS,
    'JOG_JOINT': HardwareCommand.SET_JOINTS,
    'SERVO_CARTESIAN': HardwareCommand.SET_JOINTS,
}

SOFT_COMMANDS = {'SET_MODE'}
JOINT_STREAM_PRODUCERS = frozenset({'ros2_control_backbone', 'ros2_control', 'arm_hardware_interface'})


class HardwareCommandDispatcherNode(ManagedLifecycleNode):
    """Translate high-level hardware commands into serial frames and correlated feedback."""

    def __init__(self) -> None:
        super().__init__('hardware_command_dispatcher')
        self.declare_parameter('default_completion_timeout_sec', 1.0)
        self.declare_parameter('default_ack_timeout_sec', 0.35)
        self.declare_parameter('max_retries', 2)
        self.declare_parameter('safety_limits_path', '')
        self._safety_limits = self._load_safety_limits()
        self._sequence = 0
        self._pending: dict[int, PendingCommand] = {}
        self._tx_pub = self.create_managed_publisher(String, TopicNames.HARDWARE_STM32_TX, 20)
        self._feedback_pub = self.create_managed_publisher(String, TopicNames.HARDWARE_FEEDBACK, 20)
        self._summary_pub = self.create_managed_publisher(String, TopicNames.HARDWARE_DISPATCHER_STATE, 10)
        self.create_subscription(String, TopicNames.HARDWARE_COMMAND, self._on_command, 20)
        self.create_subscription(String, TopicNames.INTERNAL_HARDWARE_CMD, self._on_command, 20)
        self.create_subscription(String, TopicNames.HARDWARE_STM32_RX, self._on_rx, 50)
        self.create_timer(0.05, self._check_pending)
        self.create_timer(0.2, self._publish_summary)
        self._stats = {'sent': 0, 'ack': 0, 'nack': 0, 'retry': 0, 'timeout': 0, 'done': 0, 'fault': 0, 'parser_error': 0, 'soft_done': 0}
        self.get_logger().info('Hardware command dispatcher is ready.')


    def _load_safety_limits(self) -> SafetyLimits:
        """Load runtime safety limits from the configured authority file."""
        configured_path = ''
        try:
            configured_path = str(self.get_parameter('safety_limits_path').value or '').strip()
        except Exception:
            configured_path = ''
        return load_safety_limits(configured_path or None)

    def _active_safety_limits(self) -> SafetyLimits:
        limits = getattr(self, '_safety_limits', None)
        if isinstance(limits, SafetyLimits):
            return limits
        limits = HardwareCommandDispatcherNode._load_safety_limits(self)
        try:
            self._safety_limits = limits
        except Exception:
            pass
        return limits

    @staticmethod
    def _command_producer(payload: Dict[str, Any]) -> str:
        producer = str(payload.get('producer', '') or '').strip()
        if producer:
            return producer
        return str(payload.get('source', '') or '').strip()

    @staticmethod
    def _validate_command_origin(payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise SafetyViolation('hardware command payload must be a dictionary')
        kind = str(payload.get('kind', '') or '')
        if kind != 'SET_JOINTS':
            return
        producer = HardwareCommandDispatcherNode._command_producer(payload)
        if producer not in JOINT_STREAM_PRODUCERS:
            raise SafetyViolation(
                'hardware_dispatcher SET_JOINTS: producer '
                f'{producer or "<empty>"} is not authorized for joint-stream transport'
            )
        command_plane = str(payload.get('command_plane', '') or '').strip()
        if command_plane and command_plane != 'joint_stream':
            raise SafetyViolation(
                'hardware_dispatcher SET_JOINTS: command_plane must be joint_stream when provided'
            )

    def _validate_command_against_safety(self, payload: Dict[str, Any]) -> None:
        """Validate one high-level hardware command against runtime safety limits.

        Args:
            payload: Decoded JSON command payload.

        Returns:
            None.

        Raises:
            SafetyViolation: If the command exceeds configured limits.
        """
        if not isinstance(payload, dict):
            raise SafetyViolation('hardware command payload must be a dictionary')
        limits = HardwareCommandDispatcherNode._active_safety_limits(self)
        kind = str(payload.get('kind', '') or '')
        if kind == 'SERVO_CARTESIAN':
            limits.require_manual_servo(
                axis=str(payload.get('axis', '') or ''),
                delta=float(payload.get('delta', 0.0) or 0.0),
                context='hardware_dispatcher SERVO_CARTESIAN',
            )
        elif kind == 'JOG_JOINT':
            limits.require_manual_jog(
                joint_index=int(payload.get('jointIndex', -1)),
                direction=int(payload.get('direction', 0)),
                step_deg=float(payload.get('stepDeg', 0.0) or 0.0),
                context='hardware_dispatcher JOG_JOINT',
            )
        elif kind == 'SET_JOINTS':
            joint_names = [str(item) for item in list(payload.get('joint_names') or [])]
            positions = [float(item) for item in list(payload.get('joint_positions') or [])]
            limits.require_joint_positions(joint_names, positions, context='hardware_dispatcher SET_JOINTS')
            if payload.get('gripper_position') is not None:
                limits.require_joint_positions(['gripper_joint'], [float(payload.get('gripper_position'))], context='hardware_dispatcher SET_JOINTS gripper')
        if kind in {'OPEN_GRIPPER', 'CLOSE_GRIPPER'} and payload.get('force') is not None:
            limits.require_gripper_force(float(payload.get('force', 0.0) or 0.0), context=f'hardware_dispatcher {kind}')
        target = payload.get('execution_target')
        if isinstance(target, dict) and target:
            limits.require_execution_target(target, context=f'hardware_dispatcher {kind or "command"}')

    @staticmethod
    def _feedback_context(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the stable correlation fields copied onto every feedback payload."""
        return {
            'command_id': str(payload.get('command_id', '') or ''),
            'plan_id': str(payload.get('plan_id', '') or ''),
            'task_id': str(payload.get('task_id', '') or ''),
            'stage': str(payload.get('stage', '') or ''),
            'kind': str(payload.get('kind', '') or ''),
            'request_id': str(payload.get('request_id', payload.get('requestId', '')) or ''),
            'correlation_id': str(payload.get('correlation_id', payload.get('correlationId', '')) or ''),
            'task_run_id': str(payload.get('task_run_id', payload.get('taskRunId', '')) or ''),
            'execution_mode': str(payload.get('execution_mode', '') or ''),
            'transport_contract': str(payload.get('transport_contract', '') or ''),
        }

    def _pending_feedback(self, pending: PendingCommand, *, status: str, sequence: int, **extra: Any) -> Dict[str, Any]:
        payload = {
            'status': str(status),
            'sequence': int(sequence),
            **self._feedback_context(pending.payload),
        }
        payload.update({key: value for key, value in extra.items() if value is not None})
        return payload

    def _payload_feedback(self, payload: Dict[str, Any], *, status: str, sequence: int, **extra: Any) -> Dict[str, Any]:
        base = {
            'status': str(status),
            'sequence': int(sequence),
            **self._feedback_context(payload),
        }
        base.update({key: value for key, value in extra.items() if value is not None})
        return base


    @staticmethod
    def _semantic_feedback(
        *,
        transport_state: str,
        transport_result: str,
        actuation_state: str,
        actuation_result: str,
        execution_state: str | None = None,
        result_code: str | None = None,
    ) -> Dict[str, str]:
        """Build compatibility-preserving feedback semantics.

        Args:
            transport_state: Transport-phase status such as sent, accepted, rejected, completed, or timeout.
            transport_result: Transport-level result marker.
            actuation_state: Execution-phase state such as pending, executing, succeeded, canceled, or fault.
            actuation_result: Execution-phase outcome marker.
            execution_state: Optional compatibility alias for older consumers.
            result_code: Optional compatibility alias for older consumers.

        Returns:
            Dict[str, str]: Fields that preserve the legacy compatibility aliases while
            separating transport and actuation semantics.
        """
        return {
            'transport_state': str(transport_state),
            'transport_result': str(transport_result),
            'actuation_state': str(actuation_state),
            'actuation_result': str(actuation_result),
            'execution_state': str(execution_state or actuation_state),
            'result_code': str(result_code or actuation_result),
        }

    def _dispatch_failure_feedback(self, payload: Dict[str, Any] | None, *, message: str) -> None:
        """Publish one immediate dispatch failure feedback payload.

        Args:
            payload: Original command payload when available.
            message: Failure detail.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        if isinstance(payload, dict):
            self._publish_feedback(self._payload_feedback(payload, status='failed', sequence=-1, message=message, source='hardware_dispatcher', **HardwareCommandDispatcherNode._semantic_feedback(transport_state='failed', transport_result='dispatch_error', actuation_state='failed', actuation_result='dispatch_error')))
            return
        self._publish_feedback({
            'status': 'failed',
            'sequence': -1,
            'command_id': '',
            'plan_id': '',
            'task_id': '',
            'stage': '',
            'kind': '',
            'request_id': '',
            'correlation_id': '',
            'task_run_id': '',
            'message': str(message),
            'source': 'hardware_dispatcher',
            **HardwareCommandDispatcherNode._semantic_feedback(transport_state='failed', transport_result='dispatch_error', actuation_state='failed', actuation_result='dispatch_error'),
        })

    def _on_command(self, msg: String) -> None:
        if not self.runtime_active:
            return
        payload: Dict[str, Any] | None = None
        try:
            payload = json.loads(msg.data)
            if not isinstance(payload, dict):
                raise ValueError('hardware command payload must be a JSON object')
            kind = str(payload.get('kind', ''))
            if kind in SOFT_COMMANDS:
                self._stats['soft_done'] += 1
                self._publish_feedback(self._payload_feedback(payload, status='done', sequence=-1, result='soft_command_applied', **HardwareCommandDispatcherNode._semantic_feedback(transport_state='soft', transport_result='soft_done', actuation_state='succeeded', actuation_result='soft_done')))
                return
            command = CMD_MAP.get(kind)
            if command is None:
                self.get_logger().warn(f'Unknown hardware command kind: {kind}')
                self._publish_feedback(self._payload_feedback(payload, status='nack', sequence=-1, message='unsupported command kind', **HardwareCommandDispatcherNode._semantic_feedback(transport_state='rejected', transport_result='unsupported_command', actuation_state='failed', actuation_result='unsupported_command')))
                return
            HardwareCommandDispatcherNode._validate_command_origin(payload)
            HardwareCommandDispatcherNode._validate_command_against_safety(self, payload)
            sequence = self._allocate_sequence()
            frame = build_frame(command, sequence, payload)
            self._pending[sequence] = PendingCommand(
                sequence=sequence,
                payload=payload,
                command=command,
                sent_at=time.monotonic(),
                ack_timeout_sec=float(payload.get('ack_timeout_sec', self.get_parameter('default_ack_timeout_sec').value)),
                completion_timeout_sec=float(payload.get('timeout_sec', self.get_parameter('default_completion_timeout_sec').value)),
            )
            self._tx_pub.publish(String(data=frame.encode().hex()))
            self._stats['sent'] += 1
            self._publish_feedback(self._payload_feedback(payload, status='sent', sequence=sequence, **HardwareCommandDispatcherNode._semantic_feedback(transport_state='sent', transport_result='sent', actuation_state='pending', actuation_result='queued', execution_state='queued', result_code='sent')))
        except Exception as exc:
            self.get_logger().error(f'Failed to dispatch hardware command: {exc}')
            self._dispatch_failure_feedback(payload, message=str(exc))

    def _allocate_sequence(self) -> int:
        sequence = self._sequence
        self._sequence = (self._sequence + 1) % 255
        return sequence

    def _on_rx(self, msg: String) -> None:
        try:
            frame = decode_hex_frame(msg.data)
            payload = decode_payload(frame.payload)
        except Exception as exc:
            self._stats['parser_error'] += 1
            self.get_logger().warn(f'Failed to decode STM32 RX frame: {exc}')
            return

        command = HardwareCommand(frame.command)
        if command == HardwareCommand.ACK:
            ack_sequence = int(payload.get('ack_sequence', frame.sequence))
            pending = self._pending.get(ack_sequence)
            if pending:
                pending.acked = True
                pending.sent_at = time.monotonic()
                self._stats['ack'] += 1
                self._publish_feedback(self._pending_feedback(pending, status='ack', sequence=ack_sequence, **HardwareCommandDispatcherNode._semantic_feedback(transport_state=str(payload.get('transport_state', 'accepted')), transport_result=str(payload.get('transport_result', payload.get('result_code', 'accepted'))), actuation_state=str(payload.get('actuation_state', payload.get('execution_state', 'pending'))), actuation_result=str(payload.get('actuation_result', payload.get('result_code', 'accepted'))), execution_state=str(payload.get('execution_state', payload.get('actuation_state', 'pending'))), result_code=str(payload.get('result_code', payload.get('transport_result', 'accepted'))))))
        elif command == HardwareCommand.NACK:
            nack_sequence = int(payload.get('ack_sequence', frame.sequence))
            pending = self._pending.pop(nack_sequence, None)
            if pending:
                self._stats['nack'] += 1
                self._publish_feedback(self._pending_feedback(
                    pending,
                    status='nack',
                    sequence=nack_sequence,
                    message=payload.get('message', 'NACK'),
                    **HardwareCommandDispatcherNode._semantic_feedback(
                        transport_state=str(payload.get('transport_state', 'rejected')),
                        transport_result=str(payload.get('transport_result', payload.get('result_code', 'nack'))),
                        actuation_state=str(payload.get('actuation_state', payload.get('execution_state', 'failed'))),
                        actuation_result=str(payload.get('actuation_result', payload.get('result_code', 'nack'))),
                        execution_state=str(payload.get('execution_state', payload.get('actuation_state', 'failed'))),
                        result_code=str(payload.get('result_code', payload.get('actuation_result', 'nack'))),
                    ),
                ))
        elif command == HardwareCommand.REPORT_STATE:
            last_sequence = int(payload.get('last_sequence', -1))
            pending = self._pending.pop(last_sequence, None)
            if pending:
                self._stats['done'] += 1
                self._publish_feedback(self._pending_feedback(
                    pending,
                    status='done',
                    sequence=last_sequence,
                    result=payload.get('last_result', 'done'),
                    stage=str(pending.payload.get('stage') or payload.get('last_stage', '')),
                    task_id=str(pending.payload.get('task_id') or payload.get('task_id', '')),
                    **HardwareCommandDispatcherNode._semantic_feedback(
                        transport_state=str(payload.get('transport_state', 'completed')),
                        transport_result=str(payload.get('transport_result', 'accepted')),
                        actuation_state=str(payload.get('actuation_state', payload.get('execution_state', 'succeeded'))),
                        actuation_result=str(payload.get('actuation_result', payload.get('result_code', payload.get('last_result', 'done')))),
                        execution_state=str(payload.get('execution_state', payload.get('actuation_state', 'succeeded'))),
                        result_code=str(payload.get('result_code', payload.get('actuation_result', payload.get('last_result', 'done')))),
                    ),
                ))
        elif command == HardwareCommand.REPORT_FAULT:
            self._stats['fault'] += 1
            source_sequence = int(payload.get('last_sequence', frame.sequence))
            pending = self._pending.pop(source_sequence, None)
            if pending is not None:
                self._publish_feedback(self._pending_feedback(
                    pending,
                    status='fault',
                    sequence=source_sequence,
                    hardware_fault_code=int(payload.get('hardware_fault_code', 0)),
                    message=payload.get('message', 'hardware fault'),
                    **HardwareCommandDispatcherNode._semantic_feedback(
                        transport_state=str(payload.get('transport_state', 'completed')),
                        transport_result=str(payload.get('transport_result', 'accepted')),
                        actuation_state=str(payload.get('actuation_state', payload.get('execution_state', 'fault'))),
                        actuation_result=str(payload.get('actuation_result', payload.get('result_code', payload.get('hardware_fault_code', 'fault')))),
                        execution_state=str(payload.get('execution_state', payload.get('actuation_state', 'fault'))),
                        result_code=str(payload.get('result_code', payload.get('actuation_result', payload.get('hardware_fault_code', 'fault')))),
                    ),
                ))
            else:
                self._publish_feedback({
                    'status': 'fault',
                    'sequence': frame.sequence,
                    'command_id': '',
                    'plan_id': '',
                    'task_id': str(payload.get('task_id', '') or ''),
                    'stage': str(payload.get('last_stage', '') or ''),
                    'kind': '',
                    'request_id': '',
                    'correlation_id': '',
                    'task_run_id': '',
                    'hardware_fault_code': int(payload.get('hardware_fault_code', 0)),
                    'message': payload.get('message', 'hardware fault'),
                    **HardwareCommandDispatcherNode._semantic_feedback(
                        transport_state=str(payload.get('transport_state', 'completed')),
                        transport_result=str(payload.get('transport_result', 'accepted')),
                        actuation_state=str(payload.get('actuation_state', payload.get('execution_state', 'fault'))),
                        actuation_result=str(payload.get('actuation_result', payload.get('result_code', payload.get('hardware_fault_code', 'fault')))),
                        execution_state=str(payload.get('execution_state', payload.get('actuation_state', 'fault'))),
                        result_code=str(payload.get('result_code', payload.get('actuation_result', payload.get('hardware_fault_code', 'fault')))),
                    ),
                })

    def _check_pending(self) -> None:
        if not self.runtime_active or not self._pending:
            return
        max_retries = int(self.get_parameter('max_retries').value)
        now = time.monotonic()
        for sequence, pending in list(self._pending.items()):
            elapsed = now - pending.sent_at
            if not pending.acked:
                if elapsed < pending.ack_timeout_sec:
                    continue
                if pending.attempts <= max_retries:
                    self._resend(sequence, pending, now)
                    continue
                self._pending.pop(sequence, None)
                self._stats['timeout'] += 1
                self._publish_feedback(self._timeout_payload(sequence, pending, 'ack timeout'))
                continue
            if elapsed < pending.completion_timeout_sec:
                continue
            self._pending.pop(sequence, None)
            self._stats['timeout'] += 1
            self._publish_feedback(self._timeout_payload(sequence, pending, 'completion timeout'))

    def _resend(self, sequence: int, pending: PendingCommand, now: float) -> None:
        frame = build_frame(pending.command, sequence, pending.payload)
        self._tx_pub.publish(String(data=frame.encode().hex()))
        pending.attempts += 1
        pending.sent_at = now
        pending.acked = False
        self._stats['retry'] += 1
        self._publish_feedback(self._pending_feedback(pending, status='retry', sequence=sequence, attempts=pending.attempts))

    def _timeout_payload(self, sequence: int, pending: PendingCommand, reason: str) -> Dict[str, Any]:
        return self._pending_feedback(pending, status='timeout', sequence=sequence, message=reason, **HardwareCommandDispatcherNode._semantic_feedback(transport_state='timeout', transport_result='timeout', actuation_state='failed', actuation_result='timeout', execution_state='failed', result_code='timeout'))

    def _publish_feedback(self, payload: Dict[str, Any]) -> None:
        self._feedback_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def _publish_summary(self) -> None:
        if not self.runtime_active:
            return
        now = time.monotonic()
        payload = {
            'pending': len(self._pending),
            'pending_details': [pending.to_summary(now) for pending in self._pending.values()],
            **self._stats,
        }
        self._summary_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))


def main(args=None) -> None:
    lifecycle_main(HardwareCommandDispatcherNode, args=args)
