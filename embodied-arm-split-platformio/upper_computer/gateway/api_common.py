from __future__ import annotations

import json
from typing import Any

from fastapi import Request, WebSocket

from .lifespan import AppContext, CTX, context_from_request, context_from_websocket
from .models import new_request_id, now_iso
from .runtime_projection import ProjectionTopic
from .security import normalize_role



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
    }
    effective_ctx = ctx or CTX
    return effective_ctx.state.append_audit(record)



def append_log(
    level: str,
    module: str,
    event: str,
    message: str,
    *,
    task_id: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
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
