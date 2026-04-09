from gateway.ros_bridge import build_pick_place_action_goal_payload, should_route_task_via_pick_place_action
from fastapi.testclient import TestClient

from gateway.server import app


def test_health_and_readiness():
    with TestClient(app) as client:
        resp = client.get('/health/live')
        assert resp.status_code == 200
        ready = client.get('/health/ready')
        assert ready.status_code == 200
        assert 'data' in ready.json()


def test_emergency_stop_is_independent_endpoint():
    with TestClient(app) as client:
        resp = client.post('/api/system/emergency-stop', headers={'X-Operator-Role': 'operator'})
        assert resp.status_code == 200
        summary = client.get('/api/system/summary').json()['data']
        assert summary['emergencyStop'] is True
        assert summary['mode'] == 'safe_stop'


def test_manual_jog_requires_maintainer_and_manual_mode():
    with TestClient(app) as client:
        blocked = client.post('/api/hardware/jog-joint', json={'jointIndex': 0, 'direction': 1, 'stepDeg': 2.0}, headers={'X-Operator-Role': 'operator'})
        assert blocked.status_code == 403
        client.post('/api/hardware/set-mode', json={'mode': 'maintenance'}, headers={'X-Operator-Role': 'maintainer'})
        ok = client.post('/api/hardware/jog-joint', json={'jointIndex': 0, 'direction': 1, 'stepDeg': 2.0}, headers={'X-Operator-Role': 'maintainer'})
        assert ok.status_code == 200


def test_start_task_is_blocked_when_task_policy_is_not_ready():
    with TestClient(app) as client:
        readiness = client.get('/health/ready').json()['data']
        assert readiness['commandPolicies']['startTask']['allowed'] is False
        response = client.post('/api/task/start', json={'taskType': 'pick_place', 'targetCategory': 'red'}, headers={'X-Operator-Role': 'operator'})
        assert response.status_code == 409


def test_websocket_initial_snapshot_contains_readiness():
    with TestClient(app) as client:
        with client.websocket_connect('/ws') as ws:
            first = ws.receive_json()
            second = ws.receive_json()
            events = {first['event'], second['event']}
            assert 'system.state.updated' in events
            assert 'readiness.state.updated' in events


def test_websocket_can_replay_recent_events():
    with TestClient(app) as client:
        client.post('/api/system/reset-fault', headers={'X-Operator-Role': 'operator'})
        with client.websocket_connect('/ws') as ws:
            for _ in range(6):
                ws.receive_json()
            ws.send_json({'event': 'client.replay_recent', 'data': {'limit': 2}})
            replayed = ws.receive_json()
            assert replayed['event'] in {'audit.event.created', 'log.event.created', 'system.state.updated', 'diagnostics.summary.updated', 'hardware.state.updated', 'readiness.state.updated'}


def test_pick_place_action_routing_only_applies_to_pick_and_place():
    assert should_route_task_via_pick_place_action('PICK_AND_PLACE') is True
    assert should_route_task_via_pick_place_action('CLEAR_TABLE') is False


def test_pick_place_action_goal_carries_target_selector_not_task_type():
    payload = build_pick_place_action_goal_payload(task_id='gw-red', target_selector='red', place_profile='bin_red', max_retry=2)
    assert payload['target_type'] == 'red'
    assert payload['place_profile'] == 'bin_red'
    assert payload['max_retry'] == 2


def test_servo_cartesian_available_in_maintenance_mode():
    with TestClient(app) as client:
        client.post('/api/hardware/set-mode', json={'mode': 'maintenance'}, headers={'X-Operator-Role': 'maintainer'})
        response = client.post('/api/hardware/servo-cartesian', json={'axis': 'x', 'delta': 0.02}, headers={'X-Operator-Role': 'maintainer'})
        assert response.status_code == 200


def test_activate_profile_calls_backend_activation(monkeypatch):
    from gateway.lifespan import CTX

    calls = []

    async def _fake_activate(*, profile_id: str):
        calls.append(profile_id)
        return {'success': True, 'message': 'activated', 'profile_id': profile_id}

    monkeypatch.setattr(CTX.ros, 'activate_calibration', _fake_activate)
    with TestClient(app) as client:
        versions = client.get('/api/calibration/profiles').json()['data']
        profile_id = versions[0]['id']
        response = client.put(f'/api/calibration/profiles/{profile_id}/activate', headers={'X-Operator-Role': 'maintainer'})
        assert response.status_code == 200
        assert calls == [profile_id]


def test_activate_profile_returns_503_when_runtime_activation_fails(monkeypatch):
    from gateway.lifespan import CTX

    async def _fake_activate(*, profile_id: str):
        return {'success': False, 'message': 'activate calibration service unavailable', 'profile_id': profile_id}

    monkeypatch.setattr(CTX.ros, 'activate_calibration', _fake_activate)
    before = CTX.storage.snapshot()
    with TestClient(app) as client:
        versions = client.get('/api/calibration/profiles').json()['data']
        profile_id = versions[0]['id']
        response = client.put(f'/api/calibration/profiles/{profile_id}/activate', headers={'X-Operator-Role': 'maintainer'})
        assert response.status_code == 503
    after = CTX.storage.snapshot()
    assert after['versions'] == before['versions']


def test_health_ready_exposes_observability_degradation_fields() -> None:
    with TestClient(app) as client:
        diagnostics = client.get('/api/diagnostics/summary').json()['data']
        observability = diagnostics['observability']
        assert 'storeFailures' in observability
        assert 'lastPersistenceError' in observability
        assert 'sinkWritable' in observability
        assert 'degraded' in observability
