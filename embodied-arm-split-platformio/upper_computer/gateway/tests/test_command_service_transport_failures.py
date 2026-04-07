import asyncio

from fastapi.testclient import TestClient

from gateway.lifespan import CTX
from gateway.ros_bridge import RosBridgeError
from gateway.server import app


def test_command_timeout_maps_to_structured_504_and_failure_audit(monkeypatch):
    async def _timeout_home():
        raise asyncio.TimeoutError()

    monkeypatch.setattr(CTX.ros, 'home', _timeout_home)
    before_audits = len(CTX.state.get_audits())
    before_logs = len(CTX.state.get_logs())
    with TestClient(app) as client:
        response = client.post('/api/system/home', headers={'X-Operator-Role': 'operator'})
    assert response.status_code == 504
    payload = response.json()
    assert payload['error'] == 'internal_error'
    assert payload['failureClass'] == 'transient_io_failure'
    assert payload['operatorActionable'] is False
    assert len(CTX.state.get_audits()) == before_audits + 1
    assert len(CTX.state.get_logs()) == before_logs + 1
    assert CTX.state.get_audits()[-1]['status'] == 'failed'
    assert CTX.state.get_audits()[-1]['action'] == 'system.home'


def test_ros_bridge_unavailable_maps_to_structured_503(monkeypatch):
    async def _unavailable_home():
        raise RosBridgeError('ROS2 service unavailable: /arm/home')

    monkeypatch.setattr(CTX.ros, 'home', _unavailable_home)
    with TestClient(app) as client:
        response = client.post('/api/system/home', headers={'X-Operator-Role': 'operator'})
    assert response.status_code == 503
    payload = response.json()
    assert payload['error'] == 'internal_error'
    assert payload['failureClass'] == 'dependency_unavailable'
    assert payload['operatorActionable'] is False
    assert payload['message'] == 'ROS2 service unavailable: /arm/home'
