from __future__ import annotations

from gateway.models import now_iso
from gateway.state import _infer_runtime_tier


def test_validated_live_requires_planner_ready_start_task_allowed_and_promotion_receipt(monkeypatch) -> None:
    readiness = {
        'motion_planner': {'planner_ready': True},
        'commandSummary': {'startTask': {'allowed': True}},
        'authoritative': True,
        'updatedAt': now_iso(),
    }
    hardware = {'simulated': False, 'sourceStm32Online': True, 'sourceStm32Authoritative': True}
    monkeypatch.setattr('gateway.state.load_runtime_promotion_receipts', lambda: {'validated_sim': True, 'validated_live': True})
    assert _infer_runtime_tier(readiness, hardware) == ('validated_live', 'Validated Live Hardware')


def test_validated_live_falls_back_to_preview_when_start_task_blocked() -> None:
    readiness = {
        'motion_planner': {'planner_ready': True},
        'commandSummary': {'startTask': {'allowed': False, 'deniedReason': 'planner_backend_unavailable'}},
        'authoritative': True,
        'updatedAt': now_iso(),
    }
    hardware = {'simulated': False, 'sourceStm32Online': True, 'sourceStm32Authoritative': True}
    assert _infer_runtime_tier(readiness, hardware) == ('preview', 'Preview / Contract Only')


def test_validated_live_receipt_missing_keeps_gateway_fail_closed(monkeypatch) -> None:
    readiness = {
        'motion_planner': {'planner_ready': True},
        'commandSummary': {'startTask': {'allowed': True}},
        'authoritative': True,
        'updatedAt': now_iso(),
    }
    hardware = {'simulated': False, 'sourceStm32Online': True, 'sourceStm32Authoritative': True}
    monkeypatch.setattr('gateway.state.load_runtime_promotion_receipts', lambda: {'validated_sim': True, 'validated_live': False})
    assert _infer_runtime_tier(readiness, hardware) == ('preview', 'Preview / Contract Only')



def test_stale_authoritative_snapshot_forces_preview_runtime_tier(monkeypatch) -> None:
    readiness = {
        'motion_planner': {'planner_ready': True},
        'commandSummary': {'startTask': {'allowed': True}},
        'authoritative': True,
        'updatedAt': '2026-01-01T00:00:00Z',
    }
    hardware = {'simulated': False, 'sourceStm32Online': True, 'sourceStm32Authoritative': True}
    monkeypatch.setattr('gateway.state.load_runtime_promotion_receipts', lambda: {'validated_sim': True, 'validated_live': True})
    assert _infer_runtime_tier(readiness, hardware) == ('preview', 'Preview / Contract Only')
