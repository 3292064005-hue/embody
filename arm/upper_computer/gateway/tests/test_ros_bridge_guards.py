from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.ros_bridge import RosBridgeError, resolve_ros_service_call, send_ros_action_goal


class _Future:
    def __init__(self, *, done: bool, result=None, error: Exception | None = None):
        self._done = done
        self._result = result
        self._error = error
        self._callbacks = []

    def add_done_callback(self, callback):
        self._callbacks.append(callback)
        if self._done:
            callback(self)

    def done(self):
        return self._done

    def result(self):
        return self._result

    def exception(self):
        return self._error


class _ServiceClient:
    def __init__(self, *, available: bool = True, future: _Future | None = None, name: str = '/svc/test'):
        self._available = available
        self._future = future or _Future(done=True, result=SimpleNamespace(success=True, message='ok'))
        self.srv_name = name

    def wait_for_service(self, timeout_sec: float):
        return self._available

    def call_async(self, request):
        return self._future


class _GoalHandle:
    def __init__(self, *, accepted: bool = True, result_future: _Future | None = None):
        self.accepted = accepted
        self._result_future = result_future or _Future(done=True, result=SimpleNamespace(result=SimpleNamespace(success=True)))

    def get_result_async(self):
        return self._result_future


class _ActionClient:
    def __init__(self, *, available: bool = True, goal_future: _Future | None = None, action_name: str = '/action/test'):
        self._available = available
        self._goal_future = goal_future or _Future(done=True, result=_GoalHandle())
        self._action_name = action_name

    def wait_for_server(self, timeout_sec: float):
        return self._available

    def send_goal_async(self, goal):
        return self._goal_future


@pytest.mark.asyncio
async def test_resolve_ros_service_call_reports_unavailable_service():
    client = _ServiceClient(available=False, name='/svc/unavailable')
    with pytest.raises(RosBridgeError, match='ROS2 service unavailable: /svc/unavailable'):
        await resolve_ros_service_call(client, object(), timeout_sec=0.01)


@pytest.mark.asyncio
async def test_resolve_ros_service_call_reports_timeout():
    client = _ServiceClient(future=_Future(done=False), name='/svc/timeout')
    with pytest.raises(RosBridgeError, match='ROS2 service timeout: /svc/timeout'):
        await resolve_ros_service_call(client, object(), timeout_sec=0.01)


@pytest.mark.asyncio
async def test_send_ros_action_goal_reports_goal_timeout():
    client = _ActionClient(goal_future=_Future(done=False), action_name='/action/timeout')
    with pytest.raises(RosBridgeError, match='action goal failed: /action/timeout'):
        await send_ros_action_goal(client, object(), wait_for_result=False, goal_timeout_sec=0.01)


@pytest.mark.asyncio
async def test_send_ros_action_goal_reports_result_timeout():
    goal_handle = _GoalHandle(result_future=_Future(done=False))
    client = _ActionClient(goal_future=_Future(done=True, result=goal_handle), action_name='/action/result-timeout')
    with pytest.raises(RosBridgeError, match='action result failed: /action/result-timeout'):
        await send_ros_action_goal(client, object(), wait_for_result=True, result_timeout_sec=0.01)
