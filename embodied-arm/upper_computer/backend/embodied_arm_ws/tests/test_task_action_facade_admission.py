from __future__ import annotations

from types import SimpleNamespace

from arm_backend_common.enums import FaultCode
from arm_task_orchestrator.node_actions import TaskActionFacade
from arm_task_orchestrator.orchestrator import OrchestratorDecision


class _GoalResponse:
    ACCEPT = 'accept'
    REJECT = 'reject'


class _CancelResponse:
    ACCEPT = 'accept'


class _Node:
    def get_parameter(self, _name):
        return SimpleNamespace(value=1.2)


def _build_facade(decision: OrchestratorDecision, *, command_decision: OrchestratorDecision | None = None) -> tuple[TaskActionFacade, dict[str, dict[str, object]]]:
    task_outcomes: dict[str, dict[str, object]] = {}
    facade = TaskActionFacade(
        node=_Node(),
        action_server_type=object,
        goal_response_type=_GoalResponse,
        cancel_response_type=_CancelResponse,
        action_names=SimpleNamespace(),
        pick_place_action_type=object,
        homing_action_type=object,
        recover_action_type=object,
        state_machine=SimpleNamespace(last_reason=''),
        orchestrator=SimpleNamespace(),
        evaluate_task_request=lambda _request: decision,
        enqueue_task_request=lambda _request: decision,
        evaluate_command_policy=(lambda _name: command_decision) if command_decision is not None else None,
        cancel_task_by_id=lambda *_args, **_kwargs: None,
        elapsed_for_task=lambda _task_id: 0.0,
        estimate_progress=lambda: 0.0,
        send_hardware_command=lambda _payload: None,
        emit_event=lambda *args, **kwargs: None,
        queue_clear=lambda: None,
        transition_to_idle=lambda _reason: None,
        task_outcomes_getter=lambda: task_outcomes,
        current_getter=lambda: None,
        phase_getter=lambda: 'IDLE',
    )
    return facade, task_outcomes


def test_pick_place_goal_callback_reuses_authoritative_task_admission_reason():
    decision = OrchestratorDecision(stage='rejected', accepted=False, message='missing readiness: target_available', fault=FaultCode.UNKNOWN)
    facade, task_outcomes = _build_facade(decision)
    response = facade.pick_place_goal_callback(SimpleNamespace(task_id='task-action', target_type='red', target_id='cube-1', place_profile='bin_red', max_retry=1))
    assert response == _GoalResponse.REJECT
    assert task_outcomes['task-action']['terminal'] is True
    assert task_outcomes['task-action']['message'] == 'missing readiness: target_available'



def test_homing_and_recover_goal_callbacks_reuse_authoritative_command_policies():
    blocked = OrchestratorDecision(stage='blocked', accepted=False, message='recover blocked by readiness', fault=FaultCode.UNKNOWN)
    accepted = OrchestratorDecision(stage='queued', accepted=True, message='task accepted', fault=FaultCode.NONE)
    facade, _ = _build_facade(accepted, command_decision=blocked)
    assert facade.homing_goal_callback(SimpleNamespace()) == _GoalResponse.REJECT
    assert facade.recover_goal_callback(SimpleNamespace()) == _GoalResponse.REJECT
