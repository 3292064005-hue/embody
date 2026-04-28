from __future__ import annotations

import json

import rclpy
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from std_srvs.srv import Trigger

from arm_backend_common.config import load_yaml
from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
from arm_common import TopicNames


class ProfileManagerNode(ManagedLifecycleNode):
    def __init__(self) -> None:
        super().__init__("profile_manager_node")
        self.declare_parameter("task_profile_path", "")
        self.declare_parameter("placement_profile_path", "")
        self.declare_parameter("publish_period_sec", 1.0)
        self._bundle = {"task_profile": {}, "placement_profiles": {}}
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self._pub = self.create_managed_publisher(String, TopicNames.PROFILES_ACTIVE, qos)
        self.create_service(Trigger, "~/reload", self._reload)
        self._load()
        self.create_timer(float(self.get_parameter("publish_period_sec").value), self._publish)

    def _load(self) -> None:
        task_profile_path = self.get_parameter("task_profile_path").get_parameter_value().string_value
        placement_profile_path = self.get_parameter("placement_profile_path").get_parameter_value().string_value
        task_cfg = load_yaml(task_profile_path).data if task_profile_path else {}
        placement_cfg = load_yaml(placement_profile_path).data if placement_profile_path else {}
        self._bundle = {
            "task_profile_path": task_profile_path,
            "placement_profile_path": placement_profile_path,
            "task_profile": task_cfg,
            "placement_profiles": placement_cfg.get("place_profiles", placement_cfg),
        }

    def _publish(self) -> None:
        if not self.runtime_active:
            return
        self._pub.publish(String(data=json.dumps(self._bundle, ensure_ascii=False)))

    def _reload(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request
        if not self.runtime_active:
            response.success = False
            response.message = 'profile manager inactive'
            return response
        try:
            self._load()
            self._publish()
            response.success = True
            response.message = "Profiles reloaded"
        except Exception as exc:
            response.success = False
            response.message = str(exc)
        return response


def main(args=None) -> None:
    lifecycle_main(ProfileManagerNode, args=args)
