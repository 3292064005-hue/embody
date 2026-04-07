from fastapi.testclient import TestClient

from gateway.server import app


def test_clear_targets_requires_maintainer_and_clears_runtime_state():
    with TestClient(app) as client:
        blocked = client.post('/api/vision/clear-targets', headers={'X-Operator-Role': 'operator'})
        assert blocked.status_code == 403
        with client.websocket_connect('/ws') as ws:
            for _ in range(6):
                ws.receive_json()
            ok = client.post('/api/vision/clear-targets', headers={'X-Operator-Role': 'maintainer'})
            assert ok.status_code == 200
            payload = ok.json()['data']
            assert payload['cleared'] >= 0
            events = [ws.receive_json()['event'] for _ in range(3)]
            assert 'vision.targets.updated' in events
            assert 'readiness.state.updated' in events


def test_readiness_required_checks_follow_operator_mode():
    with TestClient(app) as client:
        initial = client.get('/health/ready').json()['data']
        assert initial['mode'] == 'simulated_local_only'
        client.post('/api/hardware/set-mode', json={'mode': 'maintenance'}, headers={'X-Operator-Role': 'maintainer'})
        maintenance = client.get('/health/ready').json()['data']
        assert maintenance['mode'] == 'simulated_local_only'
        assert maintenance['source'] == 'gateway_dev_simulation'
        assert maintenance['commandPolicies']['jog']['allowed'] is True


def test_vision_frame_metadata_reflects_target_count():
    with TestClient(app) as client:
        frame = client.get('/api/vision/frame').json()['data']
        assert 'targetCount' in frame
        assert 'available' in frame


def test_invalid_start_task_payload_is_rejected_by_schema():
    with TestClient(app) as client:
        response = client.post('/api/task/start', json={'taskType': 'drop_table', 'targetCategory': 'red'}, headers={'X-Operator-Role': 'operator'})
        assert response.status_code == 422


def test_invalid_calibration_payload_is_rejected_by_schema():
    with TestClient(app) as client:
        response = client.put('/api/calibration/profile', json={'profileName': 'default', 'roi': {'x': 0, 'y': 0, 'width': 0, 'height': 480}, 'tableScaleMmPerPixel': 1.0, 'offsets': {'x': 0.0, 'y': 0.0, 'z': 0.0}}, headers={'X-Operator-Role': 'maintainer'})
        assert response.status_code == 422


def test_readiness_snapshot_exposes_command_policies():
    with TestClient(app) as client:
        readiness = client.get('/health/ready').json()['data']
        assert 'commandPolicies' in readiness
        assert readiness['checks']['camera_alive']['ok'] is False
        assert readiness['checks']['perception_alive']['ok'] is False
        assert readiness['checks']['target_available']['ok'] is False
        assert readiness['commandPolicies']['servoCartesian']['allowed'] is True
        assert readiness['simulated'] is True


from gateway.ros_bridge import RosBridge
from gateway.state import GatewayState


def test_calibration_activation_fallback_reports_failure_without_ros_runtime(tmp_path):
    state = GatewayState()
    bridge = RosBridge(state, lambda *_args, **_kwargs: None, tmp_path / 'default_calibration.yaml')
    bridge.available = False
    result = __import__('asyncio').run(bridge.activate_calibration(profile_id='profile-1'))
    assert result['success'] is False
    assert 'requires ROS runtime connectivity' in result['message']
    assert result['profile_id'] == 'profile-1'


def test_default_profile_remains_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv('EMBODIED_ARM_RUNTIME_PROFILE', 'target-runtime')
    monkeypatch.setenv('EMBODIED_ARM_ALLOW_SIMULATION_FALLBACK', 'false')
    state = GatewayState()
    bridge = RosBridge(state, lambda *_args, **_kwargs: None, tmp_path / 'default_calibration.yaml')
    bridge.available = False
    bridge.start()
    readiness = state.get_readiness()
    assert readiness['mode'] == 'bootstrap'
    assert readiness['commandPolicies']['home']['allowed'] is False
