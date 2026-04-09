from __future__ import annotations

import json
from pathlib import Path

import gateway.task_catalog as task_catalog
from gateway.models import map_camera_frame_summary
from gateway.observability import StructuredEventSink
from gateway.state import GatewayState
from gateway.task_catalog import public_task_templates, resolve_task_request


def test_public_task_templates_are_loaded_from_generated_catalog() -> None:
    templates = public_task_templates()
    assert len(templates) >= 5
    sort_color = next(item for item in templates if item['id'] == 'sort-color')
    assert sort_color['allowedTargetCategories'] == ['red', 'blue', 'green']
    assert sort_color['resolvedPlaceProfiles']['blue'] == 'bin_blue'
    assert sort_color['requiredRuntimeTier'] == 'validated_sim'


def test_resolve_task_request_uses_template_catalog_and_place_profile_mapping() -> None:
    resolved = resolve_task_request(template_id='sort-color', task_type='sort_by_color', target_category='green')
    assert resolved.backend_task_type == 'PICK_BY_COLOR'
    assert resolved.target_category == 'green'
    assert resolved.place_profile == 'bin_green'
    assert resolved.required_runtime_tier == 'validated_sim'


def test_resolve_task_request_rejects_mismatched_task_type() -> None:
    try:
        resolve_task_request(template_id='pick-red', task_type='clear_table', target_category='red')
    except ValueError as exc:
        assert 'templateId and taskType do not match' in str(exc)
    else:
        raise AssertionError('expected mismatched template/taskType to be rejected')


def test_task_run_ledger_persists_finished_history_when_sink_enabled(tmp_path: Path) -> None:
    sink = StructuredEventSink(tmp_path / 'obs', strict_sync=True)
    state = GatewayState(sink=sink)
    state.start_task(
        'task-ledger-1',
        'pick_place',
        'red',
        request_id='req-ledger-1',
        correlation_id='corr-ledger-1',
        task_run_id='run-ledger-1',
        template_id='pick-red',
        place_profile='bin_red',
        runtime_tier='validated_sim',
    )
    state.update_task_from_log({'taskId': 'task-ledger-1', 'event': 'PLAN_OK', 'message': 'plan ok'})
    state.update_task_from_log({'taskId': 'task-ledger-1', 'event': 'TASK_DONE', 'message': 'done'})
    history = state.get_task_history()
    assert history[0]['templateId'] == 'pick-red'
    assert history[0]['placeProfile'] == 'bin_red'
    assert history[0]['runtimeTier'] == 'validated_sim'
    assert history[0]['taskRunId'] == 'run-ledger-1'
    sink.flush()
    lines = (tmp_path / 'obs' / 'task_runs.jsonl').read_text(encoding='utf-8').strip().splitlines()
    assert any(json.loads(line)['event'] == 'task_run.finished' for line in lines)


def test_map_camera_frame_summary_exposes_provider_truth_layers() -> None:
    projected = map_camera_frame_summary(
        {
            'source': 'camera_runtime',
            'frameIngressMode': 'synthetic_frame_stream',
            'frame': {
                'sourceType': 'mock',
                'payload': {
                    'mockProfile': 'authoritative_demo',
                    'kind': 'synthetic_scene',
                    'authoritativeTargetSource': 'synthetic_perception',
                    'targets': [{'target_id': 'target-1'}],
                },
            },
        }
    )
    assert projected['available'] is True
    assert projected['frameIngressLive'] is True
    assert projected['cameraLive'] is False
    assert projected['syntheticPreview'] is True
    assert projected['providerKind'] == 'synthetic_scene'
    assert projected['authoritativeVisualSource'] == 'synthetic_perception'


def test_task_catalog_falls_back_to_generated_python_contract_when_json_artifact_missing(monkeypatch) -> None:
    original_path = task_catalog._MANIFEST_PATH
    task_catalog._manifest.cache_clear()
    task_catalog._templates_by_id.cache_clear()
    task_catalog.product_line_capabilities.cache_clear()
    task_catalog.task_capability_summary.cache_clear()
    monkeypatch.setattr(task_catalog, '_MANIFEST_PATH', original_path.with_name('runtime_contract_manifest.missing.json'))
    try:
        templates = task_catalog.public_task_templates()
        assert templates
        assert any(item['id'] == 'sort-color' for item in templates)
        capabilities = task_catalog.product_line_capabilities()
        assert capabilities['validated_sim']['taskWorkbenchVisible'] is True
    finally:
        monkeypatch.setattr(task_catalog, '_MANIFEST_PATH', original_path)
        task_catalog._manifest.cache_clear()
        task_catalog._templates_by_id.cache_clear()
        task_catalog.product_line_capabilities.cache_clear()
        task_catalog.task_capability_summary.cache_clear()


def test_map_camera_frame_summary_keeps_live_metadata_without_fake_preview() -> None:
    projected = map_camera_frame_summary(
        {
            'source': 'camera_runtime',
            'frameIngressMode': 'live_camera_stream',
            'frame': {
                'sourceType': 'topic',
                'payload': {
                    'kind': 'frame_summary',
                    'authoritativeTargetSource': 'external_topic_required',
                    'targets': [],
                },
            },
        }
    )
    assert projected['available'] is False
    assert projected['frameIngressLive'] is True
    assert projected['cameraLive'] is True
    assert projected['syntheticPreview'] is False
    assert projected['providerKind'] == 'live_frame_summary'
    assert 'renderable frame' in projected['message']
