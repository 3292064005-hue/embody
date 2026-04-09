from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.routing import APIRoute

from gateway.server import app

ROOT = Path(__file__).resolve().parents[2]


def _public_rest_paths() -> set[str]:
    paths: set[str] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if 'WS' in ''.join(route.methods or set()):
            continue
        if route.path.startswith('/openapi') or route.path.startswith('/docs') or route.path.startswith('/redoc'):
            continue
        paths.add(route.path)
    return paths


def test_runtime_api_contract_matches_public_gateway_routes() -> None:
    openapi_path = ROOT / 'gateway' / 'openapi' / 'runtime_api.yaml'
    generated_client_path = ROOT / 'frontend' / 'src' / 'api' / 'generated' / 'index.ts'
    system_service_path = ROOT / 'frontend' / 'src' / 'services' / 'api' / 'system.ts'
    task_service_path = ROOT / 'frontend' / 'src' / 'services' / 'api' / 'task.ts'

    payload = yaml.safe_load(openapi_path.read_text(encoding='utf-8')) or {}
    paths = payload.get('paths', {}) if isinstance(payload, dict) else {}
    schemas = payload.get('components', {}).get('schemas', {}) if isinstance(payload, dict) else {}

    assert set(paths.keys()) == _public_rest_paths()
    assert '/api/system/readiness' in paths
    assert '/api/task/start' in paths

    readiness = paths['/api/system/readiness']['get']
    assert '200' in readiness['responses']

    task_start = paths['/api/task/start']['post']
    request_schema = task_start['requestBody']['content']['application/json']['schema']
    assert request_schema == {'$ref': '#/components/schemas/StartTaskRequest'}
    task_request = schemas['StartTaskRequest']
    assert task_request['properties']['taskType']['enum'] == ['pick_place', 'sort_by_color', 'sort_by_qr', 'clear_table']
    target_category = task_request['properties']['targetCategory']
    enum_branch = next(item for item in target_category.get('anyOf', []) if isinstance(item, dict) and 'enum' in item)
    assert enum_branch['enum'] == ['red', 'blue', 'green', 'qr_a', 'qr_b', 'qr_c']

    generated = generated_client_path.read_text(encoding='utf-8')
    assert "systemReadiness: '/api/system/readiness'" in generated
    assert "taskStart: '/api/task/start'" in generated
    assert 'export type RuntimeReadiness' in generated
    assert 'export type StartTaskRequest' in generated
    assert 'export class RuntimeApiError extends Error' in generated
    assert 'return await unwrapResponse<RuntimeReadiness>(apiClient.get<ApiResponse<RuntimeReadiness>>(routes.systemReadiness));' in generated
    assert 'return await unwrapResponse<StartTaskDecision>(apiClient.post<ApiResponse<StartTaskDecision>>(routes.taskStart, payload));' in generated
    assert 'throw asRuntimeApiError(error);' in generated

    system_service = system_service_path.read_text(encoding='utf-8')
    task_service = task_service_path.read_text(encoding='utf-8')
    assert "from '@/api/generated'" in system_service
    assert "from '@/api/generated'" in task_service
