from arm_task_orchestrator.task_plugins import StageIOContract, resolve_task_runtime_plugin


def test_task_runtime_plugins_expose_layered_contract_components() -> None:
    plugin = resolve_task_runtime_plugin('CLEAR_TABLE')
    assert plugin.key == 'continuous'
    assert hasattr(plugin, 'target_selector')
    assert hasattr(plugin, 'stage_policy')
    assert hasattr(plugin, 'recovery_policy')
    verify_contract = plugin.stage_contract('verification')
    assert isinstance(verify_contract, StageIOContract)
    assert verify_contract.stage == 'verification'
    assert verify_contract.recovery_entrypoint == 'perception'
    assert 'verification_decision' in verify_contract.outputs


def test_selector_routed_plugin_keeps_selection_and_default_stage_recovery_split() -> None:
    plugin = resolve_task_runtime_plugin('PICK_BY_COLOR')
    assert plugin.key == 'selector_routed'
    planning_contract = plugin.stage_contract('planning')
    assert planning_contract.stage == 'planning'
    assert 'selected_target' in planning_contract.inputs
    assert planning_contract.recovery_entrypoint == 'perception'


def test_runtime_plugin_components_are_authoritative_interfaces() -> None:
    plugin = resolve_task_runtime_plugin('PICK_AND_PLACE')
    assert plugin.target_selector is not None
    assert plugin.stage_policy is not None
    assert plugin.recovery_policy is not None
    assert plugin.stage_contract('planning').inputs == ('selected_target', 'planning_request')
