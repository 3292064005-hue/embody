from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gateway.lifespan import AppContext
from gateway.models import default_system_state
from gateway.ros_bridge import RosBridge
from gateway.state import GatewayState


class _AwaitableFailureTask:
    def __init__(self) -> None:
        self.cancel_called = False

    def cancel(self) -> None:
        self.cancel_called = True

    def __await__(self):
        async def _boom():
            raise RuntimeError('heartbeat cleanup failed')

        return _boom().__await__()


class _FailingRosStop:
    def stop(self) -> None:
        raise RuntimeError('ros bridge cleanup failed')


@pytest.mark.asyncio
async def test_app_context_stop_logs_cleanup_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('EMBODIED_ARM_GATEWAY_DATA_DIR', str(tmp_path / 'gateway_data'))
    monkeypatch.setenv('EMBODIED_ARM_ACTIVE_CALIBRATION_PATH', str(tmp_path / 'gateway_data' / 'active.yaml'))
    ctx = AppContext()
    task = _AwaitableFailureTask()
    ctx.heartbeat_task = task
    ctx.ros = _FailingRosStop()

    await ctx.stop()

    assert task.cancel_called is True
    logs = ctx.state.get_logs()
    components = {record.get('payload', {}).get('component') for record in logs if record.get('event') == 'shutdown.cleanup_failed'}
    assert 'heartbeat_task' in components
    assert 'ros_bridge' in components


class _FailingExecutor:
    def shutdown(self) -> None:
        raise RuntimeError('executor shutdown failed')


class _FailingNode:
    def destroy_node(self) -> None:
        raise RuntimeError('destroy node failed')


class _FailingThread:
    def join(self, timeout: float | None = None) -> None:
        raise RuntimeError(f'thread join failed: {timeout}')


class _FailingRclpy:
    @staticmethod
    def ok() -> bool:
        return True

    @staticmethod
    def shutdown() -> None:
        raise RuntimeError('rclpy shutdown failed')


@pytest.mark.asyncio
async def test_ros_bridge_stop_logs_cleanup_failures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    bridge = RosBridge(GatewayState(), SimpleNamespace(), tmp_path / 'active.yaml')
    bridge.available = True
    bridge._executor = _FailingExecutor()
    bridge._node = _FailingNode()
    bridge._thread = _FailingThread()
    monkeypatch.setattr('gateway.ros_bridge.rclpy', _FailingRclpy)

    bridge.stop()

    assert bridge._executor is None
    assert bridge._node is None
    assert bridge._thread is None
    logs = bridge.state.get_logs()
    components = {record.get('payload', {}).get('component') for record in logs if record.get('event') == 'ros.cleanup_failed'}
    assert {'executor.shutdown', 'node.destroy_node', 'rclpy.shutdown', 'thread.join'} <= components
