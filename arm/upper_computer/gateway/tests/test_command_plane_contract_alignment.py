from fastapi.testclient import TestClient

from gateway.generated.runtime_contract import PRODUCT_LINE_CAPABILITIES
from gateway.lifespan import CTX
from gateway.security import PolicyResult
from gateway.server import app


def test_task_start_invalid_template_appends_blocked_task_control_receipt(monkeypatch) -> None:
    before = len(CTX.state.get_command_receipts())
    monkeypatch.setattr('gateway.routers.task.validate_start_task', lambda *_args, **_kwargs: PolicyResult(True, 'ok'))
    with TestClient(app) as client:
        response = client.post('/api/task/start', json={'templateId': 'missing-template'}, headers={'X-Operator-Role': 'operator'})
    assert response.status_code == 422
    receipts = CTX.state.get_command_receipts()
    assert len(receipts) == before + 1
    receipt = receipts[-1]
    assert receipt['status'] == 'blocked'
    assert receipt['commandPlane'] == 'task_control'
    assert receipt['receiptClass'] == 'workflow_command'
    assert 'missing-template' in receipt['message']


def test_manual_control_uses_contract_role_and_receipt_class_for_blocked_gripper() -> None:
    before = len(CTX.state.get_command_receipts())
    with TestClient(app) as client:
        response = client.post('/api/hardware/gripper', json={'open': True}, headers={'X-Operator-Role': 'operator'})
    assert response.status_code == 403
    receipts = CTX.state.get_command_receipts()
    assert len(receipts) == before + 1
    receipt = receipts[-1]
    assert receipt['status'] == 'blocked'
    assert receipt['commandPlane'] == 'manual_control'
    assert receipt['receiptClass'] == 'manual_command'
    assert 'requires role maintainer' in receipt['message']


def test_validated_live_product_line_is_publicly_exposed_after_promotion() -> None:
    from gateway.generated.runtime_contract import COMMAND_PLANES, TASK_CAPABILITY_REGISTRY
    assert PRODUCT_LINE_CAPABILITIES['validated_live']['publiclyExposed'] is True
    assert PRODUCT_LINE_CAPABILITIES['validated_live']['taskWorkbenchVisible'] is True
    assert COMMAND_PLANES['task_control']['entrypoint'] == 'runtime_command_gateway'
    assert COMMAND_PLANES['manual_control']['entrypoint'] == 'runtime_command_gateway'
    assert COMMAND_PLANES['system_control']['entrypoint'] == 'runtime_command_gateway'
    runtime_interfaces = TASK_CAPABILITY_REGISTRY['runtime_interfaces']
    assert runtime_interfaces[COMMAND_PLANES['task_control']['runtime_interface']]['state'] == 'active'
    assert runtime_interfaces[COMMAND_PLANES['manual_control']['runtime_interface']]['state'] == 'active'
    assert runtime_interfaces[COMMAND_PLANES['system_control']['runtime_interface']]['state'] == 'active'


def test_manual_control_blocks_when_runtime_interface_is_not_active(monkeypatch) -> None:
    before = len(CTX.state.get_command_receipts())
    monkeypatch.setattr('gateway.command_service.runtime_interface_active', lambda _name: False)
    with TestClient(app) as client:
        response = client.post('/api/hardware/gripper', json={'open': True}, headers={'X-Operator-Role': 'maintainer'})
    assert response.status_code == 422
    payload = response.json()
    assert payload['error'] == 'validation_error'
    assert payload['failureClass'] == 'contract_violation'
    receipts = CTX.state.get_command_receipts()
    assert len(receipts) == before + 1
    receipt = receipts[-1]
    assert receipt['status'] == 'blocked'
    assert receipt['commandPlane'] == 'manual_control'
    assert receipt['receiptClass'] == 'manual_command'
    assert 'runtime interface' in receipt['message']



def test_task_start_transport_failure_appends_failed_receipt_and_audit(monkeypatch) -> None:
    before_receipts = len(CTX.state.get_command_receipts())
    before_audits = len(CTX.state.get_audits())
    previous = CTX.state.get_readiness()
    updated = dict(previous)
    updated['runtimeTier'] = 'validated_sim'
    updated['allReady'] = True
    updated['modeReady'] = True
    policies = dict(updated.get('commandPolicies', {}))
    policies['startTask'] = {'allowed': True, 'reason': 'ready'}
    updated['commandPolicies'] = policies
    CTX.state.set_readiness_snapshot(updated, authoritative=bool(updated.get('authoritative', False)))
    monkeypatch.setattr('gateway.routers.task.validate_start_task', lambda *_args, **_kwargs: PolicyResult(True, 'ok'))

    class _Resolved:
        template_id = 'preview-test'
        required_runtime_tier = 'preview'
        frontend_task_type = 'pick_place'
        target_category = 'red'
        place_profile = 'bin_red'
        backend_task_type = 'PICK_AND_PLACE'
        graph_key = 'preview-test'
        plugin_key = 'single_target'

    monkeypatch.setattr('gateway.routers.task.resolve_task_request', lambda **_kwargs: _Resolved())

    async def _boom(*, command_plane: str, action: str, payload=None):
        raise RuntimeError('simulated transport explosion')

    monkeypatch.setattr(CTX.ros, 'dispatch_runtime_command', _boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post('/api/task/start', json={'templateId': 'pick-red'}, headers={'X-Operator-Role': 'operator'})
    assert response.status_code == 500
    receipts = CTX.state.get_command_receipts()
    audits = CTX.state.get_audits()
    assert len(receipts) == before_receipts + 1
    assert len(audits) == before_audits + 1
    receipt = receipts[-1]
    audit = audits[-1]
    assert receipt['status'] == 'failed'
    assert receipt['commandPlane'] == 'task_control'
    assert receipt['receiptClass'] == 'workflow_command'
    assert audit['status'] == 'failed'
    assert receipt['message'] == 'internal server error'
    CTX.state.set_readiness_snapshot(previous, authoritative=bool(previous.get('authoritative', False)))
