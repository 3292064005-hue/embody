from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.server import app


def test_system_home_returns_acceptance_semantics() -> None:
    with TestClient(app) as client:
        response = client.post('/api/system/home', headers={'X-Operator-Role': 'operator'})
    assert response.status_code == 200
    payload = response.json()['data']
    assert payload['accepted'] is True
    assert payload['commandAccepted'] is True
    assert payload['authoritativeStatus'] == 'accepted'
    assert payload['completionPending'] is True
    assert payload['operationId']
    assert payload['receiptId']


def test_manual_command_receipt_is_recorded_as_accepted() -> None:
    with TestClient(app) as client:
        client.post('/api/hardware/set-mode', json={'mode': 'maintenance'}, headers={'X-Operator-Role': 'maintainer'})
        response = client.post('/api/hardware/gripper', json={'open': True}, headers={'X-Operator-Role': 'maintainer'})
        assert response.status_code == 200
        request_id = response.json()['data']['requestId']
        receipts = client.get('/api/logs/receipts').json()['data']
    receipt = next(item for item in receipts if item['requestId'] == request_id)
    assert receipt['status'] == 'accepted'
    assert 'accepted' in receipt['message'] or 'preview' in receipt['message']



def test_system_home_preserves_legacy_success_field_without_pretending_pending_completion() -> None:
    with TestClient(app) as client:
        response = client.post('/api/system/home', headers={'X-Operator-Role': 'operator'})
    assert response.status_code == 200
    payload = response.json()['data']
    assert payload['accepted'] is True
    assert payload['success'] is False



def test_transport_result_missing_acceptance_fields_fails_closed(monkeypatch) -> None:
    from gateway.lifespan import CTX

    async def _missing_flags(*, command_plane: str, action: str, payload=None):
        assert command_plane == 'system_control'
        assert action == 'system.home'
        return {'message': 'transport forgot acceptance fields'}

    monkeypatch.setattr(CTX.ros, 'dispatch_runtime_command', _missing_flags)
    with TestClient(app) as client:
        response = client.post('/api/system/home', headers={'X-Operator-Role': 'operator'})
    assert response.status_code == 409
    payload = response.json()
    assert payload['error'] == 'readiness_blocked'
    assert 'acceptance' in payload['message'].lower() or 'rejected' in payload['message'].lower() or 'transport forgot' in payload['message'].lower()
