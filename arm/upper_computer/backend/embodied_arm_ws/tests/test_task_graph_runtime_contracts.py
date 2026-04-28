from arm_task_orchestrator.task_plugins import resolve_task_graph_contract
from arm_task_orchestrator.orchestrator import TaskOrchestrator
from arm_backend_common.data_models import TaskProfile, TaskRequest


def test_resolve_task_graph_contract_maps_templates_and_plugin_keys():
    contract = resolve_task_graph_contract('PICK_BY_COLOR', target_selector='red')
    assert contract['graphKey'] == 'sort-color'
    assert contract['pluginKey'] == 'selector_routed'
    assert contract['taskGraph']['entryNode'] == 'perception'


def test_orchestrator_begin_context_uses_graph_entry_stage_metadata():
    contract = resolve_task_graph_contract('PICK_AND_PLACE', target_selector='red')
    request = TaskRequest(task_id='task-1', task_type='PICK_AND_PLACE', target_selector='red', metadata=contract)
    context = TaskOrchestrator(TaskProfile()).begin_context(request)
    assert context.stage == 'perception'
    assert context.metadata['graphKey'] == 'pick-red'
    assert context.metadata['activeGraphNode'] == 'perception'
    assert context.metadata['activeGraphStage'] == 'perception'
