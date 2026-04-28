from __future__ import annotations

from fastapi import APIRouter, Request

from ..api_common import append_audit, publish_runtime_state, request_id_from_request, role_from_request
from ..errors import ApiException, ErrorCode
from ..lifespan import context_from_request
from ..models import new_request_id, now_iso, wrap_response
from ..schemas import CalibrationProfileRequest
from ..security import require_role

router = APIRouter()



def _ensure_runtime_activation(activation: dict, *, profile_id: str) -> dict:
    """Validate that ROS runtime activation really succeeded.

    Args:
        activation: Activation result payload returned by :class:`RosBridge`.
        profile_id: Profile identifier selected by the gateway.

    Returns:
        dict: Normalized activation payload.

    Raises:
        ApiException: Raised when the runtime did not accept the activation.
    """
    if not bool((activation or {}).get('success')):
        raise ApiException(503, str((activation or {}).get('message') or f'calibration activation unavailable for {profile_id}'), error=ErrorCode.INTERNAL_ERROR)
    return activation


@router.get('/api/calibration/profile')
async def get_calibration_profile(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_calibration(), request_id_from_request(request))


@router.get('/api/calibration/versions')
async def get_calibration_versions(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_calibration_versions(), request_id_from_request(request))


@router.get('/api/calibration/profiles')
async def get_calibration_profiles(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_calibration_versions(), request_id_from_request(request))


@router.put('/api/calibration/profile')
async def put_calibration_profile(body: CalibrationProfileRequest, request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    role = role_from_request(request)
    policy = require_role(role, 'maintainer')
    if not policy.allowed:
        append_audit('calibration.save', 'blocked', request_id, role, message=policy.reason, payload=body.model_dump(), ctx=ctx)
        raise ApiException(403, policy.reason, error=ErrorCode.FORBIDDEN)
    profile_id = new_request_id('cal')
    storage_snapshot = ctx.storage.snapshot()
    try:
        ctx.storage.save_profile({**body.model_dump(), 'updatedAt': now_iso()}, profile_id=profile_id)
        activation = _ensure_runtime_activation(await ctx.ros.activate_calibration(profile_id=profile_id), profile_id=profile_id)
    except Exception:
        ctx.storage.restore(storage_snapshot)
        raise
    runtime_profile_id = activation.get('profile_id', profile_id)
    versions_with_runtime = ctx.storage.mark_runtime_applied(runtime_profile_id, bool(activation.get('success')), str(activation.get('message', '')))
    calibration_payload = {**body.model_dump(), 'updatedAt': now_iso(), 'runtimeProfileId': runtime_profile_id}
    ctx.state.set_calibration(calibration_payload)
    ctx.state.set_calibration_versions(versions_with_runtime)
    audit = append_audit('calibration.save', 'success', request_id, role, message='calibration saved', payload={'profileId': profile_id}, ctx=ctx)
    await ctx.ws.publish('audit.event.created', audit)
    await ctx.ws.publish('calibration.profile.updated', ctx.state.get_calibration())
    await publish_runtime_state(include_calibration=True, ctx=ctx)
    return wrap_response(None, request_id)


@router.put('/api/calibration/profiles/{profile_id}/activate')
async def put_activate_profile(profile_id: str, request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    role = role_from_request(request)
    policy = require_role(role, 'maintainer')
    if not policy.allowed:
        append_audit('calibration.activate_existing', 'blocked', request_id, role, message=policy.reason, payload={'profileId': profile_id}, ctx=ctx)
        raise ApiException(403, policy.reason, error=ErrorCode.FORBIDDEN)
    storage_snapshot = ctx.storage.snapshot()
    try:
        profile, _versions = ctx.storage.activate_profile(profile_id)
        activation = _ensure_runtime_activation(await ctx.ros.activate_calibration(profile_id=profile_id), profile_id=profile_id)
    except Exception:
        ctx.storage.restore(storage_snapshot)
        raise
    runtime_profile_id = activation.get('profile_id', profile_id)
    versions_with_runtime = ctx.storage.mark_runtime_applied(runtime_profile_id, bool(activation.get('success')), str(activation.get('message', '')))
    profile_with_runtime = {**profile, 'runtimeProfileId': runtime_profile_id}
    ctx.state.set_calibration(profile_with_runtime)
    ctx.state.set_calibration_versions(versions_with_runtime)
    audit = append_audit('calibration.activate_existing', 'success', request_id, role, message='calibration profile activated', payload={'profileId': profile_id}, ctx=ctx)
    await ctx.ws.publish('audit.event.created', audit)
    await ctx.ws.publish('calibration.profile.updated', ctx.state.get_calibration())
    await publish_runtime_state(include_calibration=True, ctx=ctx)
    return wrap_response(None, request_id)


@router.post('/api/calibration/reload')
async def reload_calibration(request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    role = role_from_request(request)
    policy = require_role(role, 'maintainer')
    if not policy.allowed:
        append_audit('calibration.reload', 'blocked', request_id, role, message=policy.reason, ctx=ctx)
        raise ApiException(403, policy.reason, error=ErrorCode.FORBIDDEN)
    await ctx.ros.reload_calibration()
    audit = append_audit('calibration.reload', 'success', request_id, role, message='reload triggered', ctx=ctx)
    await ctx.ws.publish('audit.event.created', audit)
    await publish_runtime_state(include_calibration=True, ctx=ctx)
    return wrap_response(None, request_id)


@router.post('/api/calibration/activate')
async def activate_calibration(body: CalibrationProfileRequest, request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    role = role_from_request(request)
    policy = require_role(role, 'maintainer')
    if not policy.allowed:
        append_audit('calibration.activate', 'blocked', request_id, role, message=policy.reason, payload=body.model_dump(), ctx=ctx)
        raise ApiException(403, policy.reason, error=ErrorCode.FORBIDDEN)
    profile_id = new_request_id('cal')
    storage_snapshot = ctx.storage.snapshot()
    try:
        ctx.storage.save_profile({**body.model_dump(), 'updatedAt': now_iso()}, profile_id=profile_id)
        activation = _ensure_runtime_activation(await ctx.ros.activate_calibration(profile_id=profile_id), profile_id=profile_id)
    except Exception:
        ctx.storage.restore(storage_snapshot)
        raise
    runtime_profile_id = activation.get('profile_id', profile_id)
    versions_with_runtime = ctx.storage.mark_runtime_applied(runtime_profile_id, bool(activation.get('success')), str(activation.get('message', '')))
    calibration_payload = {**body.model_dump(), 'updatedAt': now_iso(), 'runtimeProfileId': runtime_profile_id}
    ctx.state.set_calibration(calibration_payload)
    ctx.state.set_calibration_versions(versions_with_runtime)
    audit = append_audit('calibration.activate', 'success', request_id, role, message='calibration profile activated', payload={'profileId': profile_id}, ctx=ctx)
    await ctx.ws.publish('audit.event.created', audit)
    await ctx.ws.publish('calibration.profile.updated', ctx.state.get_calibration())
    await publish_runtime_state(include_calibration=True, ctx=ctx)
    return wrap_response(None, request_id)
