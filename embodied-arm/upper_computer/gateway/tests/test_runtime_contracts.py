from fastapi.testclient import TestClient

from gateway.server import app


def test_clear_targets_requires_maintainer_and_clears_runtime_state():
    with TestClient(app) as client:
        blocked = client.post('/api/vision/clear-targets', headers={'X-Operator-Role': 'operator'})
        assert blocked.status_code == 403
        with client.websocket_connect('/ws') as ws:
            while True:
                frame = ws.receive_json()
                if frame.get('bootstrapComplete'):
                    break
            ok = client.post('/api/vision/clear-targets', headers={'X-Operator-Role': 'maintainer'})
            assert ok.status_code == 200
            payload = ok.json()['data']
            assert payload['cleared'] >= 0
            events: list[str] = []
            for _ in range(6):
                events.append(ws.receive_json()['event'])
                if 'vision.targets.updated' in events and 'readiness.state.updated' in events:
                    break
            assert 'vision.targets.updated' in events
            assert 'readiness.state.updated' in events


def test_readiness_required_checks_follow_operator_mode():
    with TestClient(app) as client:
        initial = client.get('/health/ready').json()['data']
        assert initial['mode'] == 'maintenance'
        client.post('/api/hardware/set-mode', json={'mode': 'maintenance'}, headers={'X-Operator-Role': 'maintainer'})
        maintenance = client.get('/health/ready').json()['data']
        assert maintenance['mode'] == 'maintenance'
        assert maintenance['source'] == 'gateway_dev_simulation'
        assert maintenance['commandPolicies']['jog']['allowed'] is True


def test_vision_frame_metadata_reflects_target_count():
    with TestClient(app) as client:
        frame = client.get('/api/vision/frame').json()['data']
        assert 'targetCount' in frame
        assert 'available' in frame
        assert 'sourceType' in frame
        if frame['available']:
            assert frame['previewDataUrl'].startswith('data:image/')


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
from gateway import state as gateway_state_module


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
    monkeypatch.setenv('EMBODIED_ARM_ENABLE_LOCAL_PREVIEW_COMMANDS', 'false')
    state = GatewayState()
    bridge = RosBridge(state, lambda *_args, **_kwargs: None, tmp_path / 'default_calibration.yaml')
    bridge.available = False
    bridge.start()
    readiness = state.get_readiness()
    assert readiness['mode'] == 'bootstrap'
    assert readiness['commandPolicies']['home']['allowed'] is False


def test_start_task_returns_current_runtime_tier_not_template_minimum_when_live_receipt_is_committed(monkeypatch):
    from gateway.lifespan import CTX

    original_readiness = CTX.state.get_readiness()
    monkeypatch.setattr(gateway_state_module, 'load_runtime_promotion_receipts', lambda: {'validated_sim': True, 'validated_live': True})
    updated = dict(original_readiness)
    updated['runtimeTier'] = 'validated_live'
    updated['authoritative'] = True
    updated['simulated'] = False
    updated['allReady'] = True
    updated['modeReady'] = True
    command_policies = dict(updated.get('commandPolicies', {}))
    start_policy = dict(command_policies.get('startTask', {}))
    start_policy['allowed'] = True
    start_policy['reason'] = 'validated live ready'
    command_policies['startTask'] = start_policy
    updated['commandPolicies'] = command_policies
    original_hardware = CTX.state.get_hardware()
    live_hardware = dict(original_hardware)
    live_hardware.update({'sourceStm32Online': True, 'sourceStm32Authoritative': True, 'sourceStm32Controllable': True})
    CTX.state.set_hardware(live_hardware)
    CTX.state.set_readiness_snapshot(updated, authoritative=True)

    async def _fake_start_task(*, task_type: str, target_selector: str, place_profile: str, auto_retry: bool, max_retry: int):
        assert task_type == 'PICK_AND_PLACE'
        assert target_selector == 'red'
        assert place_profile == 'bin_red'
        assert auto_retry is True
        assert max_retry == 2
        return {'accepted': True, 'task_id': 'gw-live-1', 'message': 'accepted'}

    monkeypatch.setattr(CTX.ros, 'start_task', _fake_start_task)
    with TestClient(app) as client:
        CTX.state.set_readiness_snapshot(updated, authoritative=True)
        response = client.post('/api/task/start', json={'templateId': 'pick-red'}, headers={'X-Operator-Role': 'operator'})
    assert response.status_code == 200
    payload = response.json()['data']
    assert payload['runtimeTier'] == 'validated_live'
    assert payload['productLine'] == 'Validated Live Hardware'
    current = CTX.state.get_current_task()
    assert current['runtimeTier'] == 'validated_live'

    CTX.state.set_readiness_snapshot(original_readiness, authoritative=True)
    CTX.state.set_hardware(original_hardware)
    CTX.state.set_current_task(None)


def test_start_task_keeps_preview_when_live_receipt_missing(monkeypatch):
    from gateway.lifespan import CTX

    original_readiness = CTX.state.get_readiness()
    original_hardware = CTX.state.get_hardware()
    monkeypatch.setattr(gateway_state_module, 'load_runtime_promotion_receipts', lambda: {'validated_sim': True, 'validated_live': False})
    updated = dict(original_readiness)
    updated['runtimeTier'] = 'validated_live'
    updated['authoritative'] = True
    updated['simulated'] = False
    updated['allReady'] = True
    updated['modeReady'] = True
    command_policies = dict(updated.get('commandPolicies', {}))
    start_policy = dict(command_policies.get('startTask', {}))
    start_policy['allowed'] = True
    start_policy['reason'] = 'validated live ready'
    command_policies['startTask'] = start_policy
    updated['commandPolicies'] = command_policies
    live_hardware = dict(original_hardware)
    live_hardware.update({'sourceStm32Online': True, 'sourceStm32Authoritative': True, 'sourceStm32Controllable': True})
    CTX.state.set_hardware(live_hardware)
    CTX.state.set_readiness_snapshot(updated, authoritative=True)

    async def _fake_start_task(*, task_type: str, target_selector: str, place_profile: str, auto_retry: bool, max_retry: int):
        return {'accepted': True, 'task_id': 'gw-live-preview', 'message': 'accepted'}

    monkeypatch.setattr(CTX.ros, 'start_task', _fake_start_task)
    with TestClient(app) as client:
        CTX.state.set_readiness_snapshot(updated, authoritative=True)
        response = client.post('/api/task/start', json={'templateId': 'pick-red'}, headers={'X-Operator-Role': 'operator'})
    assert response.status_code == 409
    payload = response.json()
    assert 'current tier is preview' in payload['message']
    readiness = CTX.state.get_readiness()
    assert readiness['runtimeTier'] == 'preview'
    current = CTX.state.get_current_task()
    assert current is None

    CTX.state.set_readiness_snapshot(original_readiness, authoritative=True)
    CTX.state.set_hardware(original_hardware)
    CTX.state.set_current_task(None)



def test_start_task_stale_authoritative_snapshot_is_readiness_blocked(monkeypatch):
    from gateway.lifespan import CTX

    previous = CTX.state.get_readiness()
    stale = dict(previous)
    stale['authoritative'] = True
    stale['simulated'] = True
    stale['allReady'] = True
    stale['modeReady'] = True
    stale['updatedAt'] = '2026-01-01T00:00:00Z'
    policies = dict(stale.get('commandPolicies', {}))
    policies['startTask'] = {'allowed': True, 'reason': 'ready'}
    stale['commandPolicies'] = policies

    async def _unexpected_start_task(**_kwargs):
        raise AssertionError('transport should not be called when authoritative readiness is stale')

    monkeypatch.setattr(CTX.ros, 'start_task', _unexpected_start_task)
    try:
        with TestClient(app) as client:
            CTX.state.set_readiness_snapshot(stale, authoritative=True)
            response = client.post('/api/task/start', json={'templateId': 'pick-red'}, headers={'X-Operator-Role': 'operator'})
        assert response.status_code == 409
        payload = response.json()
        assert payload['error'] == 'readiness_blocked'
        assert payload['message'] == 'authoritative readiness snapshot stale'
        readiness = CTX.state.get_readiness()
        assert readiness['runtimeTier'] == 'preview'
    finally:
        CTX.state.set_readiness_snapshot(previous, authoritative=bool(previous.get('authoritative', True)))


def test_manual_preview_commands_are_explicitly_labeled(monkeypatch):
    from gateway.lifespan import CTX

    monkeypatch.setenv('EMBODIED_ARM_RUNTIME_PROFILE', 'dev-hmi-mock')
    monkeypatch.setenv('EMBODIED_ARM_ALLOW_SIMULATION_FALLBACK', 'true')
    monkeypatch.setenv('EMBODIED_ARM_ENABLE_LOCAL_PREVIEW_COMMANDS', 'true')

    bridge = RosBridge(CTX.state, CTX.events, CTX.storage.active_yaml_path)
    bridge.available = False
    bridge.start()

    result = __import__('asyncio').run(bridge.command_gripper(open_gripper=True))
    assert result['localPreviewOnly'] is True
    assert result['commandMode'] == 'local_preview_only'
    assert result['success'] is True


def test_local_preview_set_mode_rejects_task_mode(tmp_path, monkeypatch):
    monkeypatch.setenv('EMBODIED_ARM_RUNTIME_PROFILE', 'dev-hmi-mock')
    monkeypatch.setenv('EMBODIED_ARM_ALLOW_SIMULATION_FALLBACK', 'true')
    monkeypatch.setenv('EMBODIED_ARM_ENABLE_LOCAL_PREVIEW_COMMANDS', 'true')
    state = GatewayState()
    bridge = RosBridge(state, lambda *_args, **_kwargs: None, tmp_path / 'default_calibration.yaml')
    bridge.available = False
    bridge.start()
    import asyncio
    try:
        asyncio.run(bridge.set_mode(mode='task'))
    except Exception as exc:
        assert 'only allows idle/manual/maintenance' in str(exc)
    else:
        raise AssertionError('expected local preview set_mode to reject task mode')
