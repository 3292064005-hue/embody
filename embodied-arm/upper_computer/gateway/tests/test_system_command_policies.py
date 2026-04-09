from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient

from gateway.lifespan import CTX
from gateway.server import app


def _blocked_readiness() -> dict:
    readiness = deepcopy(CTX.state.get_readiness())
    readiness['modeReady'] = False
    readiness['allReady'] = False
    command_policies = dict(readiness.get('commandPolicies', {}))
    command_policies['home'] = {'allowed': False, 'reason': 'home blocked for audit test'}
    command_policies['resetFault'] = {'allowed': False, 'reason': 'reset blocked for audit test'}
    command_policies['recover'] = {'allowed': False, 'reason': 'recover blocked for audit test'}
    readiness['commandPolicies'] = command_policies
    return readiness


def test_system_commands_fail_closed_against_authoritative_command_policies(monkeypatch):
    previous = deepcopy(CTX.state.get_readiness())

    async def _unexpected_call():
        raise AssertionError('transport should not be called when readiness policy blocks the command')

    monkeypatch.setattr(CTX.ros, 'home', _unexpected_call)
    monkeypatch.setattr(CTX.ros, 'reset_fault', _unexpected_call)
    monkeypatch.setattr(CTX.ros, 'recover', _unexpected_call)

    try:
        with TestClient(app) as client:
            CTX.state.set_readiness_snapshot(_blocked_readiness(), authoritative=True)
            home = client.post('/api/system/home', headers={'X-Operator-Role': 'operator'})
            reset_fault = client.post('/api/system/reset-fault', headers={'X-Operator-Role': 'operator'})
            recover = client.post('/api/system/recover', headers={'X-Operator-Role': 'operator'})
        assert home.status_code == 409
        assert home.json()['message'] == 'home blocked for audit test'
        assert reset_fault.status_code == 409
        assert reset_fault.json()['message'] == 'reset blocked for audit test'
        assert recover.status_code == 409
        assert recover.json()['message'] == 'recover blocked for audit test'
    finally:
        CTX.state.set_readiness_snapshot(previous, authoritative=bool(previous.get('authoritative', True)))



def test_stale_authoritative_snapshot_blocks_system_commands_fail_closed(monkeypatch):
    previous = deepcopy(CTX.state.get_readiness())
    stale = deepcopy(previous)
    stale['authoritative'] = True
    stale['allReady'] = True
    stale['modeReady'] = True
    stale['updatedAt'] = '2026-01-01T00:00:00Z'
    policies = dict(stale.get('commandPolicies', {}))
    policies['home'] = {'allowed': True, 'reason': 'home ready'}
    stale['commandPolicies'] = policies

    async def _unexpected_call():
        raise AssertionError('transport should not be called when authoritative readiness is stale')

    monkeypatch.setattr(CTX.ros, 'home', _unexpected_call)

    try:
        with TestClient(app) as client:
            CTX.state.set_readiness_snapshot(stale, authoritative=True)
            response = client.post('/api/system/home', headers={'X-Operator-Role': 'operator'})
        assert response.status_code == 409
        assert response.json()['message'] == 'authoritative readiness snapshot stale'
        readiness = CTX.state.get_readiness()
        assert readiness['runtimeTier'] == 'preview'
    finally:
        CTX.state.set_readiness_snapshot(previous, authoritative=bool(previous.get('authoritative', True)))


def test_stale_authoritative_snapshot_projects_public_readiness_fail_closed():
    previous = deepcopy(CTX.state.get_readiness())
    stale = deepcopy(previous)
    stale['authoritative'] = True
    stale['allReady'] = True
    stale['modeReady'] = True
    stale['runtimeHealthy'] = True
    stale['updatedAt'] = '2026-01-01T00:00:00Z'
    policies = dict(stale.get('commandPolicies', {}))
    policies['startTask'] = {'allowed': True, 'reason': 'ready'}
    policies['home'] = {'allowed': True, 'reason': 'home ready'}
    stale['commandPolicies'] = policies

    try:
        CTX.state.set_readiness_snapshot(stale, authoritative=True)
        readiness = CTX.state.get_readiness()
        assert readiness['runtimeTier'] == 'preview'
        assert readiness['runtimeHealthy'] is False
        assert readiness['modeReady'] is False
        assert readiness['allReady'] is False
        assert readiness['commandPolicies']['startTask']['allowed'] is False
        assert readiness['commandPolicies']['home']['allowed'] is False
        assert readiness['commandPolicies']['home']['reason'] == 'authoritative readiness snapshot stale'
        assert 'authoritative readiness snapshot stale' in readiness['missingDetails']
    finally:
        CTX.state.set_readiness_snapshot(previous, authoritative=bool(previous.get('authoritative', True)))
