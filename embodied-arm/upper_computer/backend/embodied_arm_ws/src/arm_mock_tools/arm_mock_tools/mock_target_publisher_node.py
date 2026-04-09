from __future__ import annotations

import itertools

import rclpy
from rclpy.node import Node

from arm_common import MsgTypes, TopicNames

TargetInfo = MsgTypes.TargetInfo


class MockTargetPublisherNode(Node):
    def __init__(self) -> None:
        super().__init__("mock_target_publisher_node")
        self.declare_parameter("period_sec", 0.8)
        self._pub = self.create_publisher(TargetInfo, TopicNames.VISION_TARGET, 10)
        self._targets = itertools.cycle([
            ("target_001", "block", "red", 0.16, 0.04),
            ("target_002", "block", "blue", 0.18, -0.03),
            ("target_003", "cylinder", "green", 0.21, 0.01),
        ])
        self.create_timer(float(self.get_parameter("period_sec").value), self._publish_once)

    def _publish_once(self) -> None:
        target_id, target_type, semantic_label, x, y = next(self._targets)
        msg = TargetInfo()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.target_id = target_id
        msg.target_type = target_type
        msg.semantic_label = semantic_label
        msg.image_u = 320.0
        msg.image_v = 240.0
        msg.table_x = x
        msg.table_y = y
        msg.yaw = 0.0
        msg.confidence = 0.95
        msg.is_valid = True
        self._pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MockTargetPublisherNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
