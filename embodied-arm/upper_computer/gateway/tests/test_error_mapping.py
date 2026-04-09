from fastapi.testclient import TestClient

from gateway.server import app


def test_gateway_error_response_exposes_stable_error_field():
    with TestClient(app) as client:
        response = client.post('/api/hardware/jog-joint', json={'jointIndex': 0, 'direction': 1, 'stepDeg': 2.0}, headers={'X-Operator-Role': 'operator'})
        assert response.status_code == 403
        payload = response.json()
        assert payload['error'] == 'forbidden'
        assert payload['code'] == 403


def test_gateway_readiness_block_maps_to_stable_error_field():
    with TestClient(app) as client:
        response = client.post('/api/task/start', json={'taskType': 'pick_place', 'targetCategory': 'red'}, headers={'X-Operator-Role': 'operator'})
        assert response.status_code == 409
        payload = response.json()
        assert payload['error'] == 'readiness_blocked'
