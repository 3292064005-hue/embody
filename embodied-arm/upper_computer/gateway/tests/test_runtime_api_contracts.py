from pathlib import Path


def test_task_start_openapi_and_frontend_client_expose_runtime_graph_fields():
    openapi = Path('gateway/openapi/runtime_api.yaml').read_text(encoding='utf-8')
    frontend_client = Path('frontend/src/api/generated/index.ts').read_text(encoding='utf-8')
    assert 'StartTaskDecisionResponse' in openapi
    for token in ('episodeId', 'pluginKey', 'graphKey'):
        assert token in openapi
        assert token in frontend_client
