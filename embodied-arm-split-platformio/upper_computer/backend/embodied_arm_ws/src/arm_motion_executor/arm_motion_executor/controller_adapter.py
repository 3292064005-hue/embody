from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    """Minimal controller adapter used to isolate command transport semantics.

    The adapter keeps a shadow state for commands that have been dispatched so
    that node-level orchestration can correlate asynchronous hardware feedback
    without depending on transport-specific details.
    """

    def __init__(self) -> None:
        """Initialize the adapter state store.

        Args:
            None.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        self._states: dict[str, dict[str, Any]] = {}

    def send_command(self, command: dict[str, Any]) -> ControllerCommandResult:
        """Send a command to the controller adapter.

        Args:
            command: Serialized command payload.

        Returns:
            ControllerCommandResult: Immediate dispatch result.

        Raises:
            ValueError: If the command does not include a non-empty ``command_id``.
        """
        if not str(command.get('command_id', '')).strip():
            raise ValueError('command must include command_id')
        command_id = str(command['command_id'])
        self._states[command_id] = {'status': 'dispatching', 'command': dict(command)}
        return ControllerCommandResult(True, 'dispatching', command_id, payload=dict(command))

    def wait_feedback(self, command_id: str) -> dict[str, Any]:
        """Return the latest known controller feedback for a command.

        Args:
            command_id: Stable command identifier.

        Returns:
            dict[str, Any]: Latest feedback snapshot.

        Raises:
            ValueError: If ``command_id`` is empty.
        """
        if not str(command_id).strip():
            raise ValueError('command_id must be non-empty')
        state = self._states.get(command_id, {'status': 'unknown'})
        return dict(state)


    def accept_feedback(self, feedback: dict[str, Any]) -> dict[str, Any]:
        """Apply controller or hardware feedback to a tracked command.

        Args:
            feedback: Feedback payload containing at least ``command_id``.

        Returns:
            dict[str, Any]: Updated controller-side state.

        Raises:
            ValueError: If ``feedback`` does not include a non-empty ``command_id``.
        """
        if not str(feedback.get('command_id', '')).strip():
            raise ValueError('feedback must include command_id')
        command_id = str(feedback['command_id'])
        state = self._states.setdefault(command_id, {})
        state.update({
            'status': str(feedback.get('status', state.get('status', 'waiting_feedback'))),
            'source': str(feedback.get('source', state.get('source', 'hardware'))),
            'message': str(feedback.get('message', state.get('message', ''))),
        })
        return dict(state)

    def cancel_command(self, command_id: str) -> dict[str, Any]:
        """Cancel a tracked command.

        Args:
            command_id: Stable command identifier.

        Returns:
            dict[str, Any]: Updated command state.

        Raises:
            ValueError: If ``command_id`` is empty.
        """
        if not str(command_id).strip():
            raise ValueError('command_id must be non-empty')
        state = self._states.setdefault(command_id, {})
        state['status'] = 'canceled'
        return dict(state)

    def read_state(self) -> dict[str, Any]:
        """Return the current controller adapter state.

        Args:
            None.

        Returns:
            dict[str, Any]: Snapshot of tracked controller commands.

        Raises:
            Does not raise.
        """
        return {key: dict(value) for key, value in self._states.items()}
