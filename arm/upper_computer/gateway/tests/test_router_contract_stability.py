from pathlib import Path

from fastapi.testclient import TestClient

from gateway.server import app


def test_gateway_server_is_router_assembled():
    text = Path('gateway/server.py').read_text(encoding='utf-8')
    assert 'include_router' in text
    assert 'health_router' in text
    assert 'system_router' in text
    assert 'task_router' in text
    assert 'hardware_router' in text
    assert 'ws_router' in text


def test_router_split_preserves_existing_paths():
    with TestClient(app) as client:
        assert client.get('/api/system/summary').status_code == 200
        assert client.get('/api/task/templates').status_code == 200
        assert client.get('/api/vision/targets').status_code == 200
        assert client.get('/api/calibration/profile').status_code == 200
        assert client.get('/api/hardware/state').status_code == 200
        assert client.get('/api/diagnostics/summary').status_code == 200
