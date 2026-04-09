from __future__ import annotations

import json
from typing import Any

import rclpy
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from std_srvs.srv import Trigger

from arm_backend_common.config import load_yaml
from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
from arm_common import ServiceNames, SrvTypes, TopicNames, MsgTypes, build_calibration_profile_message
from .transform_utils import CalibrationModel

try:
    ActivateCalibrationVersion = SrvTypes.ActivateCalibrationVersion
    CalibrationProfileMsg = MsgTypes.CalibrationProfileMsg
except Exception:
    ActivateCalibrationVersion = object
    CalibrationProfileMsg = object


class CalibrationManagerNode(ManagedLifecycleNode):
    def __init__(self) -> None:
        super().__init__('calibration_manager_node')
        self.declare_parameter('config_path', '')
        self.declare_parameter('publish_period_sec', 1.0)
        self._config_path = self.get_parameter('config_path').get_parameter_value().string_value
        self.model = CalibrationModel()
        self._last_activation_profile_id = ''
        qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL, history=HistoryPolicy.KEEP_LAST, depth=1)
        self._profile_pub = self.create_managed_publisher(String, TopicNames.CALIBRATION_PROFILE, qos)
        self._profile_typed_pub = self.create_managed_publisher(CalibrationProfileMsg, TopicNames.CALIBRATION_PROFILE_TYPED, qos) if CalibrationProfileMsg is not object else None
        self.create_service(Trigger, '~/reload', self._reload_callback)
        if ActivateCalibrationVersion is not object:
            self.create_service(ActivateCalibrationVersion, ServiceNames.ACTIVATE_CALIBRATION, self._activate_callback)
        self.create_timer(float(self.get_parameter('publish_period_sec').value), self._publish_profile)
        self._load_config()
        self.get_logger().info('Calibration manager is ready.')

    def _load_config(self) -> None:
        if not self._config_path:
            self.get_logger().warn('No calibration config provided; using safe defaults.')
            return
        cfg = load_yaml(self._config_path).data
        self.model = CalibrationModel.from_config(cfg)
        self.get_logger().info(f'Loaded calibration from {self._config_path}')

    def _publish_profile(self) -> None:
        if not self.runtime_active:
            return
        payload = {'config_path': self._config_path, 'profile': self.model.to_dict(), 'activeProfileId': self._last_activation_profile_id}
        self._profile_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
        if self._profile_typed_pub is not None:
            self._profile_typed_pub.publish(build_calibration_profile_message(payload))

    def _reload_callback(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request
        if not self.runtime_active:
            response.success = False
            response.message = 'calibration manager inactive'
            return response
        try:
            self._load_config()
            self._publish_profile()
            response.success = True
            response.message = 'Calibration reloaded'
        except Exception as exc:
            response.success = False
            response.message = str(exc)
        return response

    def _activate_callback(self, request: Any, response: Any) -> Any:
        profile_id = str(getattr(request, 'profile_id', '') or '').strip()
        if not self.runtime_active:
            response.success = False
            response.message = 'calibration manager inactive'
            if hasattr(response, 'profile_id'):
                response.profile_id = profile_id
            return response
        try:
            self._load_config()
            self._last_activation_profile_id = profile_id
            self._publish_profile()
            response.success = True
            response.message = 'Calibration profile activated'
            if hasattr(response, 'profile_id'):
                response.profile_id = profile_id
        except Exception as exc:
            response.success = False
            response.message = str(exc)
            if hasattr(response, 'profile_id'):
                response.profile_id = profile_id
        return response


def main(args=None) -> None:
    lifecycle_main(CalibrationManagerNode, args=args)
