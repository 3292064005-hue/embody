from gateway.state import GatewayState
from gateway.server import app
from fastapi.testclient import TestClient


def test_backend_readiness_snapshot_remains_authoritative_over_local_recomputation():
    state = GatewayState()
    backend_snapshot = {
        'mode': 'task',
        'allReady': False,
        'requiredChecks': ['ros2', 'camera_alive'],
        'missingChecks': ['camera_alive'],
        'missingDetails': [{'name': 'camera_alive', 'detail': 'camera_stream_stale'}],
        'checks': {
            'ros2': {'ok': True, 'effectiveOk': True, 'detail': 'online'},
            'camera_alive': {'ok': False, 'effectiveOk': False, 'detail': 'camera_stream_stale'},
        },
        'commandPolicies': {
            'startTask': {'allowed': False, 'reason': 'blocked by backend snapshot'},
        },
    }
    state.set_readiness_snapshot(backend_snapshot)
    state.set_operator_mode('maintenance')
    state.set_hardware({'joints': [0, 0, 0, 0, 0], 'gripperOpen': True, 'homed': True, 'limits': [False] * 5, 'poseName': '', 'busy': False, 'errorCode': None, 'sourceStm32Online': True, 'sourceEsp32Online': True, 'rawStatus': {}, 'lastFrameAt': None})
    readiness = state.get_readiness()
    assert readiness['mode'] == 'task'
    assert readiness['requiredChecks'] == ['ros2', 'camera_alive']
    assert readiness['missingChecks'] == ['camera_alive']
    assert readiness['commandPolicies']['startTask']['reason'] == 'blocked by backend snapshot'


def test_unhandled_gateway_exception_is_sanitized():
    @app.get('/__test__/boom')
    async def _boom_route():
        raise RuntimeError('sensitive stack detail')

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get('/__test__/boom')
    assert response.status_code == 500
    payload = response.json()
    assert payload['error'] == 'internal_error'
    assert payload['message'] == 'internal server error'
    assert 'sensitive stack detail' not in payload['detail']

    app.router.routes = [route for route in app.router.routes if getattr(route, 'path', None) != '/__test__/boom']
