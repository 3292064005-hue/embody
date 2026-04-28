from arm_backend_common.data_models import CalibrationProfile, TargetSnapshot, TaskContext
from arm_motion_planner import (
    MotionPlanner,
    build_grasp_provider,
    build_scene_provider,
    list_registered_backend_plugins,
    list_registered_pipeline_plugins,
    list_registered_provider_descriptors,
    register_postprocessor_plugin,
    register_preprocessor_plugin,
    resolve_postprocessor_plugins,
    resolve_preprocessor_plugins,
)


def test_motion_planner_runs_configurable_pre_and_post_processors() -> None:
    observed = {}

    def pre(state):
        state.metadata['preprocessed'] = True
        state.place_pose['x'] = 0.25
        return state

    def post(state, plan):
        observed['metadata'] = dict(state.metadata)
        plan[0].payload['pipelineFlag'] = 'postprocessed'
        return plan

    planner = MotionPlanner(preprocessors=(pre,), postprocessors=(post,))
    context = TaskContext(task_id='pipeline-1', task_type='pick_place', target_selector='red')
    target = TargetSnapshot(target_id='red-1', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.0, confidence=0.99)
    calibration = CalibrationProfile(place_profiles={'default': {'x': 0.2, 'y': 0.1, 'yaw': 0.0}})

    plan = planner.build_pick_place_plan(context, target, calibration)

    assert observed['metadata']['preprocessed'] is True
    assert observed['metadata']['pipelineProfile'] == 'pick_place_v1'
    assert plan[0].payload['pipelineFlag'] == 'postprocessed'
    assert plan[4].payload['x'] == 0.25
    assert plan[0].payload['planningPipelineMetadata']['preprocessed'] is True


def test_registered_pipeline_plugins_are_resolvable_by_name() -> None:
    def pre(state):
        state.metadata['customPlugin'] = 'pre'
        return state

    def post(state, plan):
        plan[-1].payload['customPlugin'] = state.metadata['customPlugin']
        return plan

    register_preprocessor_plugin('unit_test_pre', pre, replace=True)
    register_postprocessor_plugin('unit_test_post', post, replace=True)

    planner = MotionPlanner(
        preprocessors=resolve_preprocessor_plugins(['stamp_pipeline_contract', 'unit_test_pre']),
        postprocessors=resolve_postprocessor_plugins(['echo_pipeline_contract', 'unit_test_post']),
    )
    context = TaskContext(task_id='pipeline-2', task_type='pick_place', target_selector='red')
    target = TargetSnapshot(target_id='red-2', target_type='cube', semantic_label='red', table_x=0.1, table_y=0.0, confidence=0.99)
    calibration = CalibrationProfile(place_profiles={'default': {'x': 0.2, 'y': 0.1, 'yaw': 0.0}})

    plan = planner.build_pick_place_plan(context, target, calibration)

    assert plan[0].payload['planningPipelineMetadata']['pipelineContractVersion'] == 1
    assert plan[-1].payload['customPlugin'] == 'pre'


def test_registered_pipeline_and_provider_descriptors_are_serializable() -> None:
    pipeline_plugins = list_registered_pipeline_plugins()
    provider_plugins = list_registered_provider_descriptors()

    assert any(item['name'] == 'stamp_pipeline_contract' for item in pipeline_plugins['preprocessors'])
    assert any(item['name'] == 'echo_pipeline_contract' for item in pipeline_plugins['postprocessors'])
    assert any(item['name'] == 'embedded_core' for item in provider_plugins['sceneProviders'])
    assert any(item['name'] == 'runtime_service' for item in provider_plugins['graspProviders'])


def test_provider_builders_fail_closed_on_unknown_mode() -> None:
    try:
        build_scene_provider('unknown')
    except ValueError as exc:
        assert 'unsupported scene provider mode' in str(exc)
    else:  # pragma: no cover
        raise AssertionError('scene provider builder must reject unknown modes')

    try:
        build_grasp_provider('unknown')
    except ValueError as exc:
        assert 'unsupported grasp provider mode' in str(exc)
    else:  # pragma: no cover
        raise AssertionError('grasp provider builder must reject unknown modes')


def test_registered_backend_plugins_are_serializable() -> None:
    backend_plugins = list_registered_backend_plugins()

    assert any(item['name'] == 'deterministic_simulation' for item in backend_plugins)
    assert any(item['name'] == 'runtime_service_bridge' for item in backend_plugins)
    assert any(item['name'] == 'http_bridge' for item in backend_plugins)
