from __future__ import annotations

from fastapi import APIRouter, Request

from ..api_common import request_id_from_request
from ..lifespan import context_from_request
from ..models import wrap_response

router = APIRouter()


@router.get('/api/logs')
async def get_logs(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_logs(), request_id_from_request(request))


@router.get('/api/logs/events')
async def get_log_events(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_logs(), request_id_from_request(request))


@router.get('/api/logs/audit')
async def get_audit_events(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_audits(), request_id_from_request(request))


@router.get('/api/diagnostics/summary')
async def get_diagnostics_summary(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_diagnostics(), request_id_from_request(request))
