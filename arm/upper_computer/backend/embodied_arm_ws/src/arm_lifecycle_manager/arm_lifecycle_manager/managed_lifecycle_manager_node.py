from __future__ import annotations

import json
import time
from typing import Iterable

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from arm_common import MsgTypes, TopicNames, build_bringup_status_message

from .bringup_status import build_managed_lifecycle_status_payload, mark_node_state, record_cleanup_failure

try:
    from lifecycle_msgs.msg import Transition
    from lifecycle_msgs.srv import ChangeState, GetState
except Exception:
    Transition = object
    ChangeState = GetState = object

BringupStatus = MsgTypes.BringupStatus

DEFAULT_LAYERS = [
    ('profiles', ['profile_manager_node', 'calibration_manager_node']),
    ('hardware', ['stm32_serial_node', 'esp32_link_node', 'hardware_state_aggregator_node', 'hardware_command_dispatcher']),
    ('readiness', ['readiness_manager', 'safety_supervisor']),
    ('vision', ['camera_driver_node', 'perception_node']),
    ('motion', ['scene_manager', 'grasp_planner', 'motion_planner_node', 'motion_executor_node', 'task_orchestrator']),
    ('observability', ['diagnostics_summary', 'event_logger_node', 'metrics_logger_node']),
]


class ManagedLifecycleManagerNode(Node):
    """Layer-aware lifecycle supervisor for the official runtime.

    Startup is still staged layer-by-layer, but once the rollout succeeds the
    manager continues reconciling node states. A node that drifts to
    ``inactive``/``unconfigured`` is no longer silently ignored: the manager will
    try a bounded local recovery and publish the resulting blocker/fault state.
    Hard failures such as service loss remain fail-closed and visible in the
    bringup status payload.
    """

    def __init__(self) -> None:
        super().__init__('managed_lifecycle_manager_node')
        self.declare_parameter('autostart', True)
        self.declare_parameter('poll_period_sec', 0.5)
        self.declare_parameter('service_wait_timeout_sec', 1.0)
        self.declare_parameter('state_query_timeout_sec', 2.0)
        self.declare_parameter('state_change_timeout_sec', 3.0)
        self.declare_parameter('transition_retry_limit', 2)
        self.declare_parameter('monitor_after_autostart', True)
        self.declare_parameter('node_names', [name for _, layer in DEFAULT_LAYERS for name in layer])
        self._status_pub = self.create_publisher(String, TopicNames.BRINGUP_STATUS, 10)
        self._typed_status_pub = self.create_publisher(BringupStatus, TopicNames.BRINGUP_STATUS_TYPED, 10) if BringupStatus is not object else None
        self._states: dict[str, str] = {}
        self._retry_count: dict[str, int] = {}
        self._cleanup_failures: dict[str, str] = {}
        self._autostart_done = False
        self._current_layer = 'bootstrap'
        self._blocking_node = ''
        self._terminal_fault_reason = ''
        self.create_timer(float(self.get_parameter('poll_period_sec').value), self._tick)

    def _iter_node_names(self) -> Iterable[str]:
        return [str(item).strip() for item in self.get_parameter('node_names').value if str(item).strip()]

    def _layer_spec(self) -> list[tuple[str, list[str]]]:
        configured = set(self._iter_node_names())
        layers: list[tuple[str, list[str]]] = []
        for name, members in DEFAULT_LAYERS:
            active = [node for node in members if node in configured]
            if active:
                layers.append((name, active))
        extra = [node for node in configured if node not in {member for _, members in layers for member in members}]
        if extra:
            layers.append(('compatibility', extra))
        return layers

    def _publish_status_payload(self, payload: dict) -> None:
        self._status_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
        if self._typed_status_pub is not None:
            self._typed_status_pub.publish(build_bringup_status_message(payload))

    def _status_payload(self) -> dict:
        return build_managed_lifecycle_status_payload(
            stamp_monotonic=time.monotonic(),
            autostart_complete=self._autostart_done,
            current_layer=self._current_layer,
            blocking_node=self._blocking_node,
            retry_count=self._retry_count,
            terminal_fault_reason=self._terminal_fault_reason,
            layer_spec=self._layer_spec(),
            states=self._states,
            cleanup_failures=self._cleanup_failures,
            supervision_active=bool(self.get_parameter('monitor_after_autostart').value),
        )

    def _tick(self) -> None:
        if bool(self.get_parameter('autostart').value) and not self._autostart_done:
            self._autostart_done = self._startup_sequence()
        elif self._autostart_done and bool(self.get_parameter('monitor_after_autostart').value):
            self._monitor_runtime_health()
        self._publish_status_payload(self._status_payload())

    def _startup_sequence(self) -> bool:
        self._terminal_fault_reason = ''
        for layer_name, members in self._layer_spec():
            self._current_layer = layer_name
            for name in members:
                if not self._ensure_transition(name, transition_id=getattr(Transition, 'TRANSITION_CONFIGURE', 1), expected_label='inactive'):
                    self._blocking_node = name
                    self._terminal_fault_reason = f'configure failed in layer {layer_name}'
                    return False
            for name in members:
                if not self._ensure_transition(name, transition_id=getattr(Transition, 'TRANSITION_ACTIVATE', 3), expected_label='active'):
                    self._blocking_node = name
                    self._terminal_fault_reason = f'activate failed in layer {layer_name}'
                    return False
        self._blocking_node = ''
        self._current_layer = 'complete'
        return True

    def _monitor_runtime_health(self) -> None:
        """Continuously reconcile managed nodes after autostart.

        Returns:
            None.

        Raises:
            Does not raise. Any state-query or transition problem is folded into
            published blocker/fault fields.
        """
        for layer_name, members in self._layer_spec():
            for name in members:
                state = self._query_state(name)
                if state == 'active':
                    continue
                self._current_layer = layer_name
                self._blocking_node = name
                if state == 'inactive' and self._retry_count.get(name, 0) < int(self.get_parameter('transition_retry_limit').value):
                    if self._ensure_transition(name, transition_id=getattr(Transition, 'TRANSITION_ACTIVATE', 3), expected_label='active'):
                        self._blocking_node = ''
                        self._terminal_fault_reason = ''
                        continue
                elif state == 'unconfigured' and self._retry_count.get(name, 0) < int(self.get_parameter('transition_retry_limit').value):
                    configured = self._ensure_transition(name, transition_id=getattr(Transition, 'TRANSITION_CONFIGURE', 1), expected_label='inactive')
                    activated = configured and self._ensure_transition(name, transition_id=getattr(Transition, 'TRANSITION_ACTIVATE', 3), expected_label='active')
                    if activated:
                        self._blocking_node = ''
                        self._terminal_fault_reason = ''
                        continue
                self._terminal_fault_reason = f'node {name} left active state: {state}'
                return
        self._blocking_node = ''
        self._terminal_fault_reason = ''

    def _destroy_client_safely(self, node_name: str, client) -> None:
        try:
            self.destroy_client(client)
        except Exception as exc:
            record_cleanup_failure(self._cleanup_failures, self._retry_count, node_name, exc)

    def _ensure_transition(self, node_name: str, *, transition_id: int, expected_label: str) -> bool:
        current = self._query_state(node_name)
        if current == expected_label:
            return True
        change_client = self.create_client(ChangeState, f'/{node_name}/change_state')
        try:
            if not change_client.wait_for_service(timeout_sec=float(self.get_parameter('service_wait_timeout_sec').value)):
                mark_node_state(self._states, self._retry_count, node_name, 'service_unavailable')
                return False
            request = ChangeState.Request()
            request.transition.id = int(transition_id)
            future = change_client.call_async(request)
            rclpy.spin_until_future_complete(self, future, timeout_sec=float(self.get_parameter('state_change_timeout_sec').value))
            if not future.done():
                mark_node_state(self._states, self._retry_count, node_name, 'timeout')
                return False
            result = future.result()
            if result is None or not bool(getattr(result, 'success', False)):
                mark_node_state(self._states, self._retry_count, node_name, 'transition_failed')
                return False
            state = self._query_state(node_name)
            self._states[node_name] = state
            if state != expected_label:
                mark_node_state(self._states, self._retry_count, node_name, state)
                return False
            return True
        finally:
            self._destroy_client_safely(node_name, change_client)

    def _query_state(self, node_name: str) -> str:
        client = self.create_client(GetState, f'/{node_name}/get_state')
        try:
            if not client.wait_for_service(timeout_sec=float(self.get_parameter('service_wait_timeout_sec').value)):
                return mark_node_state(self._states, self._retry_count, node_name, 'service_unavailable')
            future = client.call_async(GetState.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=float(self.get_parameter('state_query_timeout_sec').value))
            if not future.done():
                return mark_node_state(self._states, self._retry_count, node_name, 'timeout')
            result = future.result()
            label = str(getattr(getattr(result, 'current_state', None), 'label', 'unknown') or 'unknown').lower()
            self._states[node_name] = label
            return label
        finally:
            self._destroy_client_safely(node_name, client)



def main(args=None) -> None:
    rclpy.init(args=args)
    node = ManagedLifecycleManagerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
