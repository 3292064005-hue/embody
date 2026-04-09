from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

_CONTROLLER_TERMINAL_STATUSES = frozenset({'done', 'failed', 'fault', 'timeout', 'canceled', 'nack'})
_CONTROLLER_STATUS_ALIASES = {
    'accepted': 'dispatching',
    'sent': 'dispatching',
    'ack': 'ack',
    'executing': 'executing',
    'done': 'done',
    'succeeded': 'done',
    'failed': 'failed',
    'fault': 'fault',
    'timeout': 'timeout',
    'canceled': 'canceled',
    'cancelled': 'canceled',
    'nack': 'nack',
}


@dataclass
class ControllerCommandResult:
    """Controller command result returned by the runtime adapter.

    Attributes:
        accepted: Whether the command was accepted for dispatch.
        state: Controller-side state after dispatch.
        command_id: Stable command identifier.
        message: Optional human-readable detail.
        payload: Optional command echo payload.
    """

    accepted: bool
    state: str
    command_id: str
    message: str = ''
    payload: dict[str, Any] = field(default_factory=dict)


class ControllerAdapter:
    """Stateful controller adapter used to correlate dispatch and feedback.

    The adapter does not talk to hardware directly. It owns the canonical shadow
    lifecycle for command identifiers so execution code can reason about status
    transitions even when transport implementations differ.
    """

    def __init__(self) -> None:
        """Initialize the adapter state store.

        Returns:
            None.
        """
        self._states: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _normalize_status(raw_status: str) -> str:
        normalized = str(raw_status or 'dispatching').strip().lower()
        return _CONTROLLER_STATUS_ALIASES.get(normalized, normalized or 'dispatching')

    def send_command(self, command: dict[str, Any]) -> ControllerCommandResult:
        """Register one outbound command as dispatching.

        Args:
            command: Serialized command payload. Must contain `command_id`.

        Returns:
            ControllerCommandResult: Immediate shadow-state result.

        Raises:
            ValueError: If the command lacks a non-empty `command_id`.
        """
        if not str(command.get('command_id', '')).strip():
            raise ValueError('command must include command_id')
        command_id = str(command['command_id'])
        state = {
            'status': 'dispatching',
            'terminal': False,
            'source': 'controller_adapter',
            'message': '',
            'command': dict(command),
            'plan_id': str(command.get('plan_id', '') or ''),
            'task_id': str(command.get('task_id', '') or ''),
            'stage': str(command.get('stage', '') or ''),
            'kind': str(command.get('kind', '') or ''),
            'sequence_hint': int(command.get('sequence_hint', 0) or 0),
            'updated_at': round(time.time(), 3),
        }
        self._states[command_id] = state
        return ControllerCommandResult(True, 'dispatching', command_id, payload=dict(command))

    def wait_feedback(self, command_id: str) -> dict[str, Any]:
        """Return the latest known controller feedback for a command.

        Args:
            command_id: Stable command identifier.

        Returns:
            dict[str, Any]: Latest feedback snapshot.

        Raises:
            ValueError: If `command_id` is empty.
        """
        if not str(command_id).strip():
            raise ValueError('command_id must be non-empty')
        state = self._states.get(command_id, {'status': 'unknown', 'terminal': False})
        return dict(state)

    def accept_feedback(self, feedback: dict[str, Any]) -> dict[str, Any]:
        """Apply controller or hardware feedback to a tracked command.

        Args:
            feedback: Feedback payload containing at least `command_id`.

        Returns:
            dict[str, Any]: Updated controller-side state.

        Raises:
            ValueError: If `feedback` does not include a non-empty `command_id`.
        """
        if not str(feedback.get('command_id', '')).strip():
            raise ValueError('feedback must include command_id')
        command_id = str(feedback['command_id'])
        state = self._states.setdefault(command_id, {'command': {}})
        status = self._normalize_status(str(feedback.get('status', state.get('status', 'dispatching'))))
        state.update({
            'status': status,
            'terminal': status in _CONTROLLER_TERMINAL_STATUSES,
            'source': str(feedback.get('source', state.get('source', 'hardware'))),
            'message': str(feedback.get('message', state.get('message', ''))),
            'result_code': str(feedback.get('result_code', state.get('result_code', status))),
            'execution_state': str(feedback.get('execution_state', state.get('execution_state', status))),
            'updated_at': round(time.time(), 3),
        })
        for key in ('plan_id', 'task_id', 'stage', 'kind', 'sequence_hint'):
            if key in feedback and feedback[key] not in (None, ''):
                state[key] = feedback[key]
        return dict(state)

    def cancel_command(self, command_id: str) -> dict[str, Any]:
        """Cancel a tracked command.

        Args:
            command_id: Stable command identifier.

        Returns:
            dict[str, Any]: Updated command state.

        Raises:
            ValueError: If `command_id` is empty.
        """
        if not str(command_id).strip():
            raise ValueError('command_id must be non-empty')
        state = self._states.setdefault(command_id, {'command': {}})
        state.update({'status': 'canceled', 'terminal': True, 'updated_at': round(time.time(), 3)})
        return dict(state)

    def read_state(self) -> dict[str, Any]:
        """Return the current controller adapter state.

        Returns:
            dict[str, Any]: Snapshot of tracked controller commands.
        """
        return {key: dict(value) for key, value in self._states.items()}
