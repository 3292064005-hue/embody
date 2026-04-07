from __future__ import annotations
try:
    import rclpy
    from rclpy.node import Node
    from arm_msgs.msg import TargetInfo
    from std_msgs.msg import String
except Exception:  # pragma: no cover
    rclpy = None; Node = object; TargetInfo = object; String = object
import json

class VisionNode(Node):
    def __init__(self) -> None:
        super().__init__('vision_node')
        self.declare_parameter('publish_period_sec', 0.5)
        self.declare_parameter('emit_mock_targets', True)
        self.declare_parameter('mock_targets_json', '[{"target_id":"t_red","target_type":"cube","semantic_label":"red","table_x":0.12,"table_y":0.18,"yaw":0.0,"confidence":0.94},{"target_id":"t_blue","target_type":"cube","semantic_label":"blue","table_x":0.08,"table_y":-0.16,"yaw":0.0,"confidence":0.91}]')
        self._target_pub = self.create_publisher(TargetInfo, '/arm/vision/target', 20)
        self._readiness_pub = self.create_publisher(String, '/arm/readiness/update', 10)
        self._summary_pub = self.create_publisher(String, '/arm/vision/summary', 10)
        self._targets = self._load_targets()
        self._index = 0
        self.create_timer(float(self.get_parameter('publish_period_sec').value), self._tick)
    def _load_targets(self) -> list[dict]:
        raw = str(self.get_parameter('mock_targets_json').value)
        try:
            value = json.loads(raw)
            if isinstance(value, list):
                return [dict(item) for item in value]
        except Exception:
            pass
        return []
    def _tick(self) -> None:
        emit_targets = bool(self.get_parameter('emit_mock_targets').value)
        self._readiness_pub.publish(String(data=json.dumps({'check': 'camera', 'ok': True, 'detail': 'camera_ready'}, ensure_ascii=False)))
        self._summary_pub.publish(String(data=json.dumps({'emitMockTargets': emit_targets, 'targetCount': len(self._targets)}, ensure_ascii=False)))
        if not emit_targets or not self._targets:
            return
        payload = self._targets[self._index % len(self._targets)]
        self._index += 1
        msg = TargetInfo()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.target_id = str(payload.get('target_id','target'))
        msg.target_type = str(payload.get('target_type','cube'))
        msg.semantic_label = str(payload.get('semantic_label','unknown'))
        msg.image_u = float(payload.get('image_u', 320.0))
        msg.image_v = float(payload.get('image_v', 240.0))
        msg.table_x = float(payload.get('table_x', 0.0))
        msg.table_y = float(payload.get('table_y', 0.0))
        msg.yaw = float(payload.get('yaw', 0.0))
        msg.confidence = float(payload.get('confidence', 0.9))
        msg.is_valid = True
        self._target_pub.publish(msg)

def main() -> None:  # pragma: no cover
    if rclpy is None:
        raise RuntimeError('rclpy unavailable')
    rclpy.init(); node = VisionNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node(); rclpy.shutdown()
