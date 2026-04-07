from __future__ import annotations

import json

import rclpy
from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
from std_msgs.msg import String

from arm_common import TopicNames


class Esp32LinkNode(ManagedLifecycleNode):
    def __init__(self) -> None:
        super().__init__("esp32_link_node")
        self.declare_parameter("mode", "wifi")
        self.declare_parameter("stream_endpoint", "")
        self.declare_parameter("online", True)
        self._mode = self.get_parameter("mode").value
        self._stream_endpoint = self.get_parameter("stream_endpoint").value
        self._online = bool(self.get_parameter("online").value)
        self._heartbeat_counter = 0
        self._status_pub = self.create_managed_publisher(String, TopicNames.HARDWARE_ESP32_LINK, 10)
        self.create_timer(1.0, self._heartbeat)
        self.get_logger().info(f"ESP32 link node ready in {self._mode} mode.")

    def _heartbeat(self) -> None:
        if not self.runtime_active:
            return
        self._heartbeat_counter += 1
        payload = json.dumps({
            "online": self._online,
            "mode": self._mode,
            "stream_endpoint": self._stream_endpoint,
            "heartbeat_counter": self._heartbeat_counter,
        }, ensure_ascii=False)
        self._status_pub.publish(String(data=payload))


def main(args=None) -> None:
    lifecycle_main(Esp32LinkNode, args=args)
