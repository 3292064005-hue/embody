from __future__ import annotations

import json
from typing import Any

from fastapi import Request, WebSocket

from .lifespan import AppContext, CTX, context_from_request, context_from_websocket
from .models import new_request_id, now_iso
from .runtime_projection import ProjectionTopic
from .security import normalize_role


def _build_trace_envelope(
    *,
    request_id: str | None,
    correlation_id: str | None,
    task_id: str | None = None,
    task_run_id: str | None = None,
    episode_id: str | None = None,
    stage: str | None = None,
    error_code: str | None = None,
    operator_actionable: bool | None = None,
) -> dict[str, Any]:
    return {
        'requestId': str(request_id or ''),
        'correlationId': str(correlation_id or ''),
        'taskId': str(task_id or ''),
        'taskRunId': str(task_run_id or ''),
        'episodeId': str(episode_id or task_run_id or ''),
        'stage': str(stage or ''),
        'errorCode': str(error_code or ''),
        'operatorActionable': operator_actionable,
        'schemaVersion': '1.0',
    }

def request_id_from_request(request: Request) -> str:
    """Return the effective request identifier for the current request."""
    return request.headers.get('X-Request-Id', '').strip() or new_request_id()



def role_from_request(request: Request) -> str:
    """Return the normalized operator role from request headers."""
    return normalize_role(request.headers.get('X-Operator-Role'))



def append_audit(
    action: str,
    status: str,
    request_id: str,
    role: str,
    *,
    message: str,
    payload: dict[str, Any] | None = None,
    task_id: str | None = None,
    correlation_id: str | None = None,
    task_run_id: str | None = None,
    episode_id: str | None = None,
    stage: str | None = None,
    error_code: str | None = None,
    operator_actionable: bool | None = None,
    ctx: AppContext | None = None,
) -> dict[str, Any]:
    """Append and return an audit record."""
    record = {
        'id': new_request_id('audit'),
        'timestamp': now_iso(),
        'action': action,
        'status': status,
        'role': role,
        'requestId': request_id,
        'correlationId': correlation_id,
        'taskId': task_id,
        'stage': stage,
        'errorCode': error_code,
        'operatorActionable': operator_actionable,
        'message': message,
        'payload': payload or {},
        'traceEnvelope': _build_trace_envelope(
            request_id=request_id,
            correlation_id=correlation_id,
            task_id=task_id,
            task_run_id=task_run_id,
            episode_id=episode_id,
            stage=stage,
            error_code=error_code,
            operator_actionable=operator_actionable,
        ),
    }
    effective_ctx = ctx or CTX
    return effective_ctx.state.append_audit(record)



def append_command_receipt(
    action: str,
    status: str,
    request_id: str,
    role: str,
    *,
    command_plane: str,
    receipt_class: str,
    execution_bound: bool,
    message: str,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    task_run_id: str | None = None,
    episode_id: str | None = None,
    error_code: str | None = None,
    operator_actionable: bool | None = None,
    ctx: AppContext | None = None,
) -> dict[str, Any]:
    """Append and return one normalized command-receipt record.

    Args:
        action: Stable command action name.
        status: success / failed / observed / blocked style lifecycle status.
        request_id: External request identifier.
        role: Effective operator role.
        command_plane: Canonical command-plane name from runtime authority.
        receipt_class: Workflow/control/observability receipt class.
        execution_bound: Whether this event is bound to an execution path.
        message: Human-readable status summary.
        payload: Optional structured payload.
        correlation_id: Optional distributed trace id.
        error_code: Optional stable error taxonomy.
        operator_actionable: Whether the receipt represents an operator-fixable state.
        ctx: Optional application context override.

    Returns:
        dict[str, Any]: Persisted command receipt payload.

    Raises:
        Does not raise. Persistence errors are tracked by the state store.
    """
    record = {
        'id': new_request_id('receipt'),
        'timestamp': now_iso(),
        'action': action,
        'status': status,
        'role': role,
        'requestId': request_id,
        'correlationId': correlation_id,
        'commandPlane': command_plane,
        'receiptClass': receipt_class,
        'executionBound': bool(execution_bound),
        'errorCode': error_code,
        'operatorActionable': operator_actionable,
        'message': message,
        'payload': payload or {},
        'traceEnvelope': _build_trace_envelope(
            request_id=request_id,
            correlation_id=correlation_id,
            task_run_id=task_run_id,
            episode_id=episode_id,
            error_code=error_code,
            operator_actionable=operator_actionable,
        ),
    }
    effective_ctx = ctx or CTX
    return effective_ctx.state.append_command_receipt(record)


def append_log(
    level: str,
    module: str,
    event: str,
    message: str,
    *,
    task_id: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    task_run_id: str | None = None,
    episode_id: str | None = None,
    payload: dict[str, Any] | None = None,
    stage: str | None = None,
    error_code: str | None = None,
    operator_actionable: bool | None = None,
    ctx: AppContext | None = None,
) -> dict[str, Any]:
    """Append and return a log record."""
    record = {
        'id': new_request_id('log'),
        'timestamp': now_iso(),
        'level': level,
        'module': module,
        'taskId': task_id,
        'requestId': request_id,
        'correlationId': correlation_id,
        'stage': stage,
        'errorCode': error_code,
        'operatorActionable': operator_actionable,
        'event': event,
        'message': message,
        'payload': payload or {},
        'traceEnvelope': _build_trace_envelope(
            request_id=request_id,
            correlation_id=correlation_id,
            task_id=task_id,
            task_run_id=task_run_id,
            episode_id=episode_id,
            stage=stage,
            error_code=error_code,
            operator_actionable=operator_actionable,
        ),
    }
    effective_ctx = ctx or CTX
    return effective_ctx.state.append_log(record)


async def publish_runtime_state(
    *,
    include_system: bool = False,
    include_hardware: bool = False,
    include_task: bool = False,
    include_targets: bool = False,
    include_calibration: bool = False,
    ctx: AppContext | None = None,
) -> None:
    """Publish the latest runtime projections to all websocket subscribers."""
    topics: list[ProjectionTopic] = []
    if include_system:
        topics.append('system')
    if include_hardware:
        topics.append('hardware')
    if include_task:
        topics.append('task')
    if include_targets:
        topics.append('targets')
    if include_calibration:
        topics.append('calibration')
    topics.extend(['readiness', 'diagnostics'])
    effective_ctx = ctx or CTX
    await effective_ctx.events.publish_topics(*topics)


async def send_ws_initial_snapshot(websocket: WebSocket, *, ctx: AppContext | None = None) -> None:
    """Send the initial WS snapshot to a newly connected client."""
    effective_ctx = ctx or context_from_websocket(websocket)
    await effective_ctx.events.send_initial_snapshot(websocket)


async def handle_ws_client_message(websocket: WebSocket, raw: str, *, ctx: AppContext | None = None) -> None:
    """Handle a single inbound websocket client message."""
    effective_ctx = ctx or context_from_websocket(websocket)
    try:
        payload = json.loads(raw)
    except Exception:
        return
    if payload.get('event') == 'client.ping':
        await websocket.send_text(
            json.dumps(
                {
                    'event': 'server.pong',
                    'timestamp': now_iso(),
                    'source': 'gateway',
                    'schemaVersion': '1.1',
                    'data': {'sentAt': now_iso()},
                },
                ensure_ascii=False,
            )
        )
    elif payload.get('event') == 'client.replay_recent':
        await effective_ctx.ws.replay_recent(websocket, limit=int(payload.get('data', {}).get('limit', 5)))
