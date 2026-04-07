from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Request, WebSocket

from .models import coerce_system_state_aliases, default_system_state
from .observability import StructuredEventSink
from .ros_bridge import RosBridge
from .runtime_projection import RuntimeProjectionService
from .runtime_publisher import RuntimeEventPublisher
from .state import GatewayState
from .storage import CalibrationStorage
from .ws_manager import WebSocketManager




def _default_runtime_state_root(project_root: Path) -> Path:
    """Resolve the default mutable runtime-state root outside the source tree.

    Args:
        project_root: Repository root used only for compatibility fallbacks.

    Returns:
        Filesystem path used for mutable runtime state.
    """
    explicit = os.environ.get('EMBODIED_ARM_STATE_ROOT')
    if explicit:
        return Path(explicit)
    xdg_state_home = os.environ.get('XDG_STATE_HOME')
    if xdg_state_home:
        return Path(xdg_state_home) / 'embodied-arm'
    return Path.home() / '.local' / 'state' / 'embodied-arm'


class AppContext:
    """Gateway application context shared by routers and websocket handlers."""

    def __init__(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        state_root = _default_runtime_state_root(project_root)
        storage_root = Path(os.environ.get('EMBODIED_ARM_GATEWAY_DATA_DIR', state_root / 'gateway_data'))
        observability_root = Path(os.environ.get('EMBODIED_ARM_OBSERVABILITY_DIR', state_root / 'gateway_observability'))
        active_calibration_path = Path(
            os.environ.get('EMBODIED_ARM_ACTIVE_CALIBRATION_PATH', storage_root / 'active_calibration.yaml')
        )
        default_calibration_source = Path(
            os.environ.get(
                'EMBODIED_ARM_DEFAULT_CALIBRATION_SOURCE',
                project_root / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'default_calibration.yaml',
            )
        )
        self.observability = StructuredEventSink.from_environment(observability_root)
        self.state = GatewayState(sink=self.observability)
        self.ws = WebSocketManager()
        self.storage = CalibrationStorage(storage_root, active_calibration_path, default_yaml_path=default_calibration_source)
        self.projection = RuntimeProjectionService(self.state)
        self.events = RuntimeEventPublisher(self.ws, self.projection)
        self.ros = RosBridge(self.state, self.events, active_calibration_path)
        self.heartbeat_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Initialize storage, event loop bindings, and ROS connectivity.

        Args:
            None.

        Returns:
            None.

        Raises:
            Does not raise directly. Bootstrap failures are downgraded into
            internal logs so the gateway can stay online in fallback mode.
        """
        self.events.set_loop(asyncio.get_running_loop())
        profile = self.storage.load_active_profile()
        versions = self.storage.load_versions()
        self.state.set_calibration(profile)
        self.state.set_calibration_versions(versions)
        self.state.refresh_diagnostics()
        try:
            self.ros.start()
        except Exception as exc:  # pragma: no cover - defensive bootstrap logging
            self.state.append_log(
                {
                    'id': 'log-bootstrap',
                    'timestamp': self.state.timestamp(),
                    'level': 'warn',
                    'module': 'gateway.bootstrap',
                    'taskId': None,
                    'requestId': None,
                    'correlationId': None,
                    'event': 'ros.start_failed',
                    'message': str(exc),
                    'payload': {'exceptionType': exc.__class__.__name__},
                }
            )
        if not self.ros.available:
            system = default_system_state()
            system['runtimePhase'] = 'idle' if getattr(self.ros, '_simulated_runtime_active', False) else 'boot'
            system['controllerMode'] = 'maintenance' if getattr(self.ros, '_simulated_runtime_active', False) else 'idle'
            system['taskStage'] = 'created'
            system['faultMessage'] = 'ROS2 bridge unavailable; explicit dev-hmi-mock simulated runtime active.' if getattr(self.ros, '_simulated_runtime_active', False) else 'ROS2 bridge unavailable; gateway remains fail-closed until runtime connectivity is restored.'
            self.state.set_system(coerce_system_state_aliases(system))
        self.heartbeat_task = asyncio.create_task(self._heartbeat())

    async def _heartbeat(self) -> None:
        """Publish low-frequency health projections and websocket pong frames.

        Boundary behavior:
            The heartbeat updates diagnostics locally but does not rebroadcast the
            full runtime snapshot on every tick, which avoids racing the initial
            websocket bootstrap sequence.
        """
        while True:
            await asyncio.sleep(2.0)
            self.state.refresh_diagnostics()
            await self.ws.publish('server.pong', {'sentAt': self.state.timestamp()})

    def _record_cleanup_failure(self, component: str, exc: BaseException) -> None:
        """Record a best-effort shutdown/cleanup failure.

        Args:
            component: Logical component name that failed during cleanup.
            exc: Exception raised by the cleanup step.

        Returns:
            None.

        Raises:
            Does not raise. Logging failures are suppressed so shutdown can
            continue releasing the remaining resources.
        """
        try:
            self.state.append_log(
                {
                    'id': 'log-shutdown-cleanup',
                    'timestamp': self.state.timestamp(),
                    'level': 'warn',
                    'module': 'gateway.shutdown',
                    'taskId': None,
                    'requestId': None,
                    'correlationId': None,
                    'event': 'shutdown.cleanup_failed',
                    'message': str(exc),
                    'payload': {'component': component, 'exceptionType': exc.__class__.__name__},
                }
            )
        except Exception:
            pass

    async def stop(self) -> None:
        """Stop the gateway runtime and best-effort background tasks.

        Returns:
            None.

        Raises:
            Does not raise. Cleanup failures are logged internally and the
            method continues releasing the remaining resources.
        """
        heartbeat_task = self.heartbeat_task
        self.heartbeat_task = None
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            except BaseException as exc:
                self._record_cleanup_failure('heartbeat_task', exc)
        try:
            self.ros.stop()
        except Exception as exc:
            self._record_cleanup_failure('ros_bridge', exc)
        if self.observability is not None:
            try:
                self.observability.close()
            except Exception as exc:
                self._record_cleanup_failure('observability', exc)


CTX = AppContext()



def get_app_context(holder: Any | None = None) -> AppContext:
    """Resolve the effective application context from a FastAPI holder.

    Args:
        holder: FastAPI ``Request``/``WebSocket``/``app`` object, or ``None``.

    Returns:
        AppContext: The app-scoped context when available, otherwise the legacy
        module-level compatibility context.

    Raises:
        Does not raise.
    """
    if holder is None:
        return CTX
    app = getattr(holder, 'app', holder)
    state = getattr(app, 'state', None)
    ctx = getattr(state, 'ctx', None)
    return ctx if isinstance(ctx, AppContext) else CTX



def context_from_request(request: Request) -> AppContext:
    return get_app_context(request)



def context_from_websocket(websocket: WebSocket) -> AppContext:
    return get_app_context(websocket)


@asynccontextmanager
async def lifespan(app):
    app.state.ctx = CTX
    await CTX.start()
    try:
        yield
    finally:
        await CTX.stop()
