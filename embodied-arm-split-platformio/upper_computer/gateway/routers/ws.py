from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..api_common import handle_ws_client_message, send_ws_initial_snapshot
from ..lifespan import context_from_websocket

router = APIRouter()


@router.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket) -> None:
    ctx = context_from_websocket(websocket)
    await ctx.ws.connect(websocket)
    try:
        await send_ws_initial_snapshot(websocket, ctx=ctx)
        while True:
            raw = await websocket.receive_text()
            await handle_ws_client_message(websocket, raw, ctx=ctx)
    except WebSocketDisconnect:
        await ctx.ws.disconnect(websocket)
