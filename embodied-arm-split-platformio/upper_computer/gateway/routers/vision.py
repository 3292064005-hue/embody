from __future__ import annotations

from fastapi import APIRouter, Request

from ..api_common import append_audit, publish_runtime_state, request_id_from_request, role_from_request
from ..errors import ApiException, ErrorCode
from ..lifespan import context_from_request
from ..models import wrap_response
from ..security import require_role

router = APIRouter()


@router.get('/api/vision/targets')
async def get_targets(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_targets(), request_id_from_request(request))


@router.get('/api/vision/frame')
async def get_frame(request: Request):
    ctx = context_from_request(request)
    return wrap_response({'available': False, 'message': 'frame stream not persisted in gateway sandbox', 'targetCount': len(ctx.state.get_targets())}, request_id_from_request(request))


@router.post('/api/vision/clear-targets')
async def clear_targets(request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    role = role_from_request(request)
    policy = require_role(role, 'maintainer')
    if not policy.allowed:
        append_audit('vision.clear_targets', 'blocked', request_id, role, message=policy.reason, ctx=ctx)
        raise ApiException(403, policy.reason, error=ErrorCode.FORBIDDEN)
    cleared = ctx.state.clear_targets()
    audit = append_audit('vision.clear_targets', 'success', request_id, role, message=f'cleared {cleared} targets', payload={'cleared': cleared}, ctx=ctx)
    await ctx.ws.publish('audit.event.created', audit)
    await publish_runtime_state(include_targets=True, ctx=ctx)
    return wrap_response({'cleared': cleared}, request_id)
