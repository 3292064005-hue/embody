from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from arm_backend_common.data_models import TaskRequest
from arm_backend_common.enums import FaultCode
from arm_task_orchestrator.orchestrator import OrchestratorDecision


@dataclass
class ActionServerSet:
    pick_place: Any = None
    homing: Any = None
    recover: Any = None


class TaskActionFacade:
    """Own action-server lifecycle and action request/result helpers."""

    def __init__(
        self,
        *,
        node: Any,
        action_server_type,
        goal_response_type,
        cancel_response_type,
        action_names,
        pick_place_action_type,
        homing_action_type,
        recover_action_type,
        state_machine,
        orchestrator,
        evaluate_task_request: Callable[[TaskRequest], OrchestratorDecision],
        enqueue_task_request: Callable[[TaskRequest], OrchestratorDecision],
        evaluate_command_policy: Callable[[str], OrchestratorDecision] | None,
        cancel_task_by_id: Callable[[str, str], None],
        elapsed_for_task: Callable[[str], float],
        estimate_progress: Callable[[], float],
        send_hardware_command: Callable[[dict[str, Any]], None],
        emit_event: Callable[..., None],
        queue_clear: Callable[[], None],
        transition_to_idle: Callable[[str], Any],
        task_outcomes_getter: Callable[[], dict[str, dict[str, Any]]],
        current_getter: Callable[[], Any],
        phase_getter: Callable[[], str],
    ) -> None:
        self._node = node
        self._ActionServer = action_server_type
        self._GoalResponse = goal_response_type
        self._CancelResponse = cancel_response_type
        self._ActionNames = action_names
        self._PickPlaceTaskAction = pick_place_action_type
        self._HomingAction = homing_action_type
        self._RecoverAction = recover_action_type
        self._state_machine = state_machine
        self._orchestrator = orchestrator
        self._evaluate_task_request = evaluate_task_request
        self._enqueue_task_request = enqueue_task_request
        self._evaluate_command_policy = evaluate_command_policy
        self._cancel_task_by_id = cancel_task_by_id
        self._elapsed_for_task = elapsed_for_task
        self._estimate_progress = estimate_progress
        self._send_hardware_command = send_hardware_command
        self._emit_event = emit_event
        self._queue_clear = queue_clear
        self._transition_to_idle = transition_to_idle
        self._task_outcomes_getter = task_outcomes_getter
        self._current_getter = current_getter
        self._phase_getter = phase_getter
        self._servers = ActionServerSet()

    @property
    def servers(self) -> ActionServerSet:
        return self._servers

    def create_servers(self) -> ActionServerSet:
        self._servers = ActionServerSet()
        if self._ActionServer is object:
            return self._servers
        if self._PickPlaceTaskAction is not object:
            self._servers.pick_place = self._ActionServer(
                self._node,
                self._PickPlaceTaskAction,
                self._ActionNames.PICK_PLACE_TASK,
                execute_callback=self.execute_pick_place_action,
                goal_callback=self.pick_place_goal_callback,
                cancel_callback=self.pick_place_cancel_callback,
            )
        if self._HomingAction is not object:
            self._servers.homing = self._ActionServer(
                self._node,
                self._HomingAction,
                self._ActionNames.HOMING,
                execute_callback=self.execute_homing_action,
                goal_callback=self.homing_goal_callback,
                cancel_callback=lambda _goal: self._CancelResponse.ACCEPT,
            )
        if self._RecoverAction is not object:
            self._servers.recover = self._ActionServer(
                self._node,
                self._RecoverAction,
                self._ActionNames.RECOVER,
                execute_callback=self.execute_recover_action,
                goal_callback=self.recover_goal_callback,
                cancel_callback=lambda _goal: self._CancelResponse.ACCEPT,
            )
        return self._servers

    @staticmethod
    def build_pick_place_request_from_action(action_request: Any, *, task_id: str) -> TaskRequest:
        raw_target_type = str(getattr(action_request, 'target_type', '') or '').strip()
        raw_target_id = str(getattr(action_request, 'target_id', '') or '').strip()
        legacy_task_type = {
            'pick_place': 'pick_place',
            'pick_and_place': 'pick_place',
            'sort_by_color': 'sort_by_color',
            'pick_by_color': 'sort_by_color',
            'sort_by_qr': 'sort_by_qr',
            'pick_by_qr': 'sort_by_qr',
            'clear_table': 'clear_table',
        }.get(raw_target_type.lower())
        task_type = legacy_task_type or 'pick_place'
        target_selector = raw_target_id if legacy_task_type else (raw_target_type or raw_target_id)
        return TaskRequest(
            task_id=task_id,
            task_type=task_type,
            target_selector=target_selector,
            place_profile=str(getattr(action_request, 'place_profile', '') or 'default'),
            auto_retry=True,
            max_retry=max(0, int(getattr(action_request, 'max_retry', 0) or 0)),
        )

    def pick_place_goal_callback(self, goal_request) -> Any:
        task_id = str(getattr(goal_request, 'task_id', '') or '').strip() or f'task-{uuid.uuid4().hex[:8]}'
        queued = self.build_pick_place_request_from_action(goal_request, task_id=task_id)
        decision = self._evaluate_task_request(queued)
        task_outcomes = self._task_outcomes_getter()
        task_outcomes[task_id] = {
            'terminal': not decision.accepted,
            'state': 'rejected' if not decision.accepted else 'queued',
            'message': decision.message,
            'result_code': int(decision.fault),
        }
        return self._GoalResponse.ACCEPT if decision.accepted else self._GoalResponse.REJECT

    def pick_place_cancel_callback(self, goal_handle) -> Any:
        task_id = str(getattr(goal_handle.request, 'task_id', '') or '')
        self._cancel_task_by_id(task_id, 'Action cancel requested')
        return self._CancelResponse.ACCEPT

    def _evaluate_named_command(self, command_name: str) -> OrchestratorDecision:
        if self._evaluate_command_policy is None:
            return OrchestratorDecision(stage='ready', accepted=True, message='ready', fault=FaultCode.NONE)
        return self._evaluate_command_policy(command_name)

    def homing_goal_callback(self, _goal_request) -> Any:
        decision = self._evaluate_named_command('home')
        return self._GoalResponse.ACCEPT if decision.accepted else self._GoalResponse.REJECT

    def recover_goal_callback(self, _goal_request) -> Any:
        decision = self._evaluate_named_command('recover')
        return self._GoalResponse.ACCEPT if decision.accepted else self._GoalResponse.REJECT

    async def execute_pick_place_action(self, goal_handle):
        request = goal_handle.request
        task_id = str(getattr(request, 'task_id', '') or '').strip() or f'task-{uuid.uuid4().hex[:8]}'
        queued = self.build_pick_place_request_from_action(request, task_id=task_id)
        decision = self._enqueue_task_request(queued)
        if not decision.accepted:
            goal_handle.abort()
            return self.build_pick_place_result(False, decision.fault, decision.message, 0.0)
        while True:
            outcome = self._task_outcomes_getter().get(task_id, {'state': 'queued', 'message': 'queued', 'terminal': False, 'result_code': 0})
            if goal_handle.is_cancel_requested:
                self._cancel_task_by_id(task_id, 'Action cancel requested')
                goal_handle.canceled()
                return self.build_pick_place_result(False, FaultCode.UNKNOWN, 'action canceled', self._elapsed_for_task(task_id))
            goal_handle.publish_feedback(self.build_pick_place_feedback(task_id))
            if outcome.get('terminal'):
                success = outcome.get('state') == 'succeeded'
                if success:
                    goal_handle.succeed()
                elif outcome.get('state') == 'canceled':
                    goal_handle.canceled()
                else:
                    goal_handle.abort()
                return self.build_pick_place_result(
                    success,
                    int(outcome.get('result_code', 0) or 0),
                    str(outcome.get('message', '')),
                    self._elapsed_for_task(task_id),
                )
            await asyncio.sleep(0.05)

    async def execute_homing_action(self, goal_handle):
        decision = self._evaluate_named_command('home')
        if not decision.accepted:
            goal_handle.abort()
            return self.build_stateful_action_result(self._HomingAction, False, 'blocked', decision.message)
        self._send_hardware_command({'kind': 'HOME', 'task_id': 'action-home', 'timeout_sec': 1.0})
        await asyncio.sleep(0.1)
        if goal_handle.is_cancel_requested:
            goal_handle.canceled()
            return self.build_stateful_action_result(self._HomingAction, False, 'canceled', 'home canceled')
        goal_handle.succeed()
        return self.build_stateful_action_result(self._HomingAction, True, 'idle', 'home command sent')

    async def execute_recover_action(self, goal_handle):
        decision = self._evaluate_named_command('recover')
        if not decision.accepted:
            goal_handle.abort()
            return self.build_stateful_action_result(self._RecoverAction, False, 'blocked', decision.message)
        self._queue_clear()
        self._send_hardware_command({'kind': 'RESET_FAULT', 'task_id': 'action-recover', 'timeout_sec': 0.6})
        await asyncio.sleep(0.1)
        if goal_handle.is_cancel_requested:
            goal_handle.canceled()
            return self.build_stateful_action_result(self._RecoverAction, False, 'canceled', 'recover canceled')
        self._transition_to_idle('Recover action completed')
        goal_handle.succeed()
        return self.build_stateful_action_result(self._RecoverAction, True, 'idle', 'recover completed')

    def build_pick_place_feedback(self, task_id: str):
        feedback = self._PickPlaceTaskAction.Feedback()
        current = self._current_getter()
        if current is not None and current.task_id == task_id:
            feedback.stage = str(current.stage or self._phase_getter())
            feedback.progress = float(self._estimate_progress())
            feedback.message = str(self._state_machine.last_reason)
            feedback.retry_count = int(current.current_retry)
            return feedback
        outcome = self._task_outcomes_getter().get(task_id, {})
        feedback.stage = str(outcome.get('state', 'queued'))
        feedback.progress = 100.0 if outcome.get('terminal') else 0.0
        feedback.message = str(outcome.get('message', 'queued'))
        feedback.retry_count = 0
        return feedback

    def build_pick_place_result(self, success: bool, result_code: int | FaultCode, message: str, total_time: float):
        result = self._PickPlaceTaskAction.Result()
        result.success = bool(success)
        result.result_code = int(result_code)
        result.message = str(message)
        result.total_time = float(total_time)
        return result

    @staticmethod
    def build_stateful_action_result(action_type, success: bool, final_state: str, message: str):
        result = action_type.Result()
        result.success = bool(success)
        result.final_state = str(final_state)
        result.message = str(message)
        return result
