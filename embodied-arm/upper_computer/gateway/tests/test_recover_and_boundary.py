from fastapi.testclient import TestClient

from gateway.server import app


def test_reset_fault_and_recover_clear_emergency_stop_and_fault_state():
    with TestClient(app) as client:
        estop = client.post('/api/system/emergency-stop', headers={'X-Operator-Role': 'operator'})
        assert estop.status_code == 200
        summary = client.get('/api/system/summary').json()['data']
        assert summary['emergencyStop'] is True
        reset = client.post('/api/system/reset-fault', headers={'X-Operator-Role': 'operator'})
        assert reset.status_code == 200
        recovered = client.post('/api/system/recover', headers={'X-Operator-Role': 'operator'})
        assert recovered.status_code == 200
        summary = client.get('/api/system/summary').json()['data']
        assert summary['emergencyStop'] is False
        assert summary['faultCode'] in (None, '')
        assert summary['mode'] == 'idle'
