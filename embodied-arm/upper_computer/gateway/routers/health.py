from __future__ import annotations

from fastapi import APIRouter, Request

from ..lifespan import context_from_request
from ..models import new_request_id, now_iso, wrap_response

router = APIRouter()


@router.get('/health/live')
async def live():
    return {'status': 'ok', 'timestamp': now_iso()}


@router.get('/health/ready')
async def ready(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_readiness(), new_request_id('health'))


@router.get('/health/deps')
async def deps(request: Request):
    ctx = context_from_request(request)
    return wrap_response({'ros2Available': ctx.ros.available, 'simulationFallback': True, 'targetCount': len(ctx.state.get_targets())}, new_request_id('health'))
