from __future__ import annotations

import json
from typing import Any

try:
    import rclpy
    from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
    from std_msgs.msg import String
    from arm_common import (
        MsgTypes,
        SrvTypes,
        TopicNames,
        build_readiness_state_message,
        parse_calibration_profile_message,
    )
    try:
        from controller_manager_msgs.srv import ListControllers, ListHardwareComponents
    except Exception:  # pragma: no cover - optional outside ros2_control deployments.
        ListControllers = object
        ListHardwareComponents = object
    CalibrationProfileMsg = MsgTypes.CalibrationProfileMsg
    HardwareState = MsgTypes.HardwareState
    ReadinessState = MsgTypes.ReadinessState
    TargetInfo = MsgTypes.TargetInfo
except Exception:  # pragma: no cover
    rclpy = None
    ManagedLifecycleNode = object

    def lifecycle_main(factory, args=None):
        del factory, args
        raise RuntimeError('rclpy unavailable')
    String = object
    CalibrationProfileMsg = object
    HardwareState = object
    ReadinessState = object
    TargetInfo = object
    ListControllers = object
    ListHardwareComponents = object

    def build_readiness_state_message(payload):
        raise TypeError('ReadinessState unavailable')

    def parse_calibration_profile_message(msg):
        return {}

    class TopicNames:
        READINESS_STATE = '/arm/readiness/state'
        READINESS_STATE_TYPED = '/arm/readiness/state_typed'
        BRINGUP_STATUS = '/arm/bringup/status'
        READINESS_UPDATE = '/arm/readiness/update'
        HARDWARE_STATE = '/arm/hardware/state'
        CALIBRATION_PROFILE = '/arm/calibration/profile'
        CALIBRATION_PROFILE_TYPED = '/arm/calibration/profile_typed'
        PROFILES_ACTIVE = '/arm/profiles/active'
        VISION_TARGET = '/arm/vision/target'

from .readiness import ReadinessManager


class ReadinessManagerNode(ManagedLifecycleNode):
    """Aggregate authoritative runtime readiness checks and publish one snapshot.

    The node consumes existing readiness publishers and actively polls the
    ros2_control controller-manager services when those service types are
    available. Controller-manager polling is fail-closed for validated-live
    authority health: unavailable services, missing required controllers, or
    inactive hardware components keep the `controller_manager` check false.
    """

    def __init__(self) -> None:
        super().__init__('readiness_manager')
        self.declare_parameter('publish_period_sec', 0.5)
        self.declare_parameter('camera_stale_sec', 2.0)
        self.declare_parameter('controller_manager_namespace', '/controller_manager')
        self.declare_parameter('controller_state_poll_period_sec', 1.0)
        self.declare_parameter('required_active_controllers', ['arm_joint_trajectory_controller', 'gripper_command_controller'])
        self.declare_parameter('required_active_hardware_components', ['EmbodiedArmSystem'])
        self._manager = ReadinessManager()
        self._pub = self.create_managed_publisher(String, TopicNames.READINESS_STATE, 10)
        self._typed_pub = self.create_managed_publisher(ReadinessState, TopicNames.READINESS_STATE_TYPED, 10) if ReadinessState is not object else None
        self._bringup_pub = self.create_managed_publisher(String, TopicNames.BRINGUP_STATUS, 10)
        self.create_subscription(String, TopicNames.READINESS_UPDATE, self._on_update, 50)
        self.create_subscription(HardwareState, TopicNames.HARDWARE_STATE, self._on_hardware, 20)
        self.create_subscription(String, TopicNames.CALIBRATION_PROFILE, self._on_calibration, 20)
        if CalibrationProfileMsg is not object:
            self.create_subscription(CalibrationProfileMsg, TopicNames.CALIBRATION_PROFILE_TYPED, self._on_calibration_typed, 20)
        self.create_subscription(String, TopicNames.PROFILES_ACTIVE, self._on_profiles, 20)
        self.create_subscription(TargetInfo, TopicNames.VISION_TARGET, self._on_target, 20)
        self._controller_poll_pending = False
        self._hardware_poll_pending = False
        self._controller_manager_observation: dict[str, Any] = {
            'controllers': {},
            'hardwareComponents': {},
            'controllersObserved': False,
            'hardwareObserved': False,
            'servicesAvailable': False,
        }
        self._controller_clients = self._make_controller_manager_clients()
        self.create_timer(float(self.get_parameter('publish_period_sec').value), self._publish)
        self.create_timer(float(self.get_parameter('controller_state_poll_period_sec').value), self._poll_controller_manager)
        self._manager.update('ros2', True, 'node_started')

    def _controller_manager_namespace(self) -> str:
        namespace = str(self.get_parameter('controller_manager_namespace').value or '/controller_manager').strip()
        namespace = namespace.rstrip('/')
        return namespace or '/controller_manager'

    def _service_name(self, service: str) -> str:
        return f'{self._controller_manager_namespace()}/{service}'

    @staticmethod
    def _as_string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    def _required_controllers(self) -> list[str]:
        return self._as_string_list(self.get_parameter('required_active_controllers').value)

    def _required_hardware_components(self) -> list[str]:
        return self._as_string_list(self.get_parameter('required_active_hardware_components').value)

    def _make_controller_manager_clients(self) -> dict[str, Any]:
        if ListControllers is object or ListHardwareComponents is object:
            self._manager.update('controller_manager', False, 'controller_manager_msgs_unavailable', 2.5)
            return {}
        return {
            'controllers': self.create_client(ListControllers, self._service_name('list_controllers')),
            'hardware': self.create_client(ListHardwareComponents, self._service_name('list_hardware_components')),
        }

    def _poll_controller_manager(self) -> None:
        """Poll ros2_control controller-manager state without blocking the executor.

        Args:
            None.

        Returns:
            None.

        Raises:
            Does not raise; service or response errors are converted into a
            fail-closed readiness detail.

        Boundary behavior:
            Missing controller-manager services make validated-live authority
            health false, but they do not stop preview/simulation publishing.
        """
        if not self.runtime_active:
            return
        if not self._controller_clients:
            self._manager.update('controller_manager', False, 'controller_manager_clients_unavailable', 2.5)
            return
        controllers_client = self._controller_clients['controllers']
        hardware_client = self._controller_clients['hardware']
        controllers_available = bool(controllers_client.wait_for_service(timeout_sec=0.0))
        hardware_available = bool(hardware_client.wait_for_service(timeout_sec=0.0))
        self._controller_manager_observation['servicesAvailable'] = controllers_available and hardware_available
        if not controllers_available or not hardware_available:
            self._manager.update('controller_manager', False, 'controller_manager_service_unavailable', 2.5)
            return
        if not self._controller_poll_pending:
            self._controller_poll_pending = True
            future = controllers_client.call_async(ListControllers.Request())
            future.add_done_callback(self._on_list_controllers_done)
        if not self._hardware_poll_pending:
            self._hardware_poll_pending = True
            future = hardware_client.call_async(ListHardwareComponents.Request())
            future.add_done_callback(self._on_list_hardware_done)

    @staticmethod
    def _state_label(value: Any) -> str:
        label = getattr(value, 'label', None)
        if label:
            return str(label).strip().lower()
        return str(value or '').strip().lower()

    def _on_list_controllers_done(self, future: Any) -> None:
        self._controller_poll_pending = False
        try:
            response = future.result()
            controllers = getattr(response, 'controller', []) or []
            observed: dict[str, dict[str, str]] = {}
            for controller in controllers:
                name = str(getattr(controller, 'name', '') or '').strip()
                if not name:
                    continue
                observed[name] = {
                    'state': str(getattr(controller, 'state', '') or '').strip().lower(),
                    'type': str(getattr(controller, 'type', '') or '').strip(),
                }
            self._controller_manager_observation['controllers'] = observed
            self._controller_manager_observation['controllersObserved'] = True
            self._update_controller_manager_readiness()
        except Exception as exc:
            self._manager.update('controller_manager', False, f'list_controllers_failed:{exc}', 2.5)

    def _on_list_hardware_done(self, future: Any) -> None:
        self._hardware_poll_pending = False
        try:
            response = future.result()
            components = getattr(response, 'component', []) or []
            observed: dict[str, dict[str, str]] = {}
            for component in components:
                name = str(getattr(component, 'name', '') or '').strip()
                if not name:
                    continue
                observed[name] = {
                    'state': self._state_label(getattr(component, 'state', '')),
                    'type': str(getattr(component, 'type', '') or '').strip(),
                    'pluginName': str(getattr(component, 'plugin_name', '') or '').strip(),
                }
            self._controller_manager_observation['hardwareComponents'] = observed
            self._controller_manager_observation['hardwareObserved'] = True
            self._update_controller_manager_readiness()
        except Exception as exc:
            self._manager.update('controller_manager', False, f'list_hardware_components_failed:{exc}', 2.5)

    def _update_controller_manager_readiness(self) -> None:
        required_controllers = self._required_controllers()
        required_hardware = self._required_hardware_components()
        controllers = dict(self._controller_manager_observation.get('controllers', {}))
        hardware_components = dict(self._controller_manager_observation.get('hardwareComponents', {}))
        missing_controllers = [name for name in required_controllers if name not in controllers]
        inactive_controllers = [name for name in required_controllers if name in controllers and controllers[name].get('state') != 'active']
        missing_hardware = [name for name in required_hardware if name not in hardware_components]
        inactive_hardware = [name for name in required_hardware if name in hardware_components and hardware_components[name].get('state') != 'active']
        observed = bool(self._controller_manager_observation.get('controllersObserved')) and bool(self._controller_manager_observation.get('hardwareObserved'))
        ok = bool(observed and not missing_controllers and not inactive_controllers and not missing_hardware and not inactive_hardware)
        detail_payload = {
            'source': 'controller_manager_services',
            'servicesAvailable': bool(self._controller_manager_observation.get('servicesAvailable')),
            'controllersObserved': bool(self._controller_manager_observation.get('controllersObserved')),
            'hardwareObserved': bool(self._controller_manager_observation.get('hardwareObserved')),
            'requiredControllers': required_controllers,
            'missingControllers': missing_controllers,
            'inactiveControllers': inactive_controllers,
            'requiredHardwareComponents': required_hardware,
            'missingHardwareComponents': missing_hardware,
            'inactiveHardwareComponents': inactive_hardware,
        }
        self._manager.update('controller_manager', ok, json.dumps(detail_payload, sort_keys=True), 2.5)

    def _on_update(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        if isinstance(payload.get('checks'), dict):
            bulk: dict[str, tuple[bool, str] | tuple[bool, str, float | None]] = {}
            for name, item in payload['checks'].items():
                if not isinstance(item, dict):
                    continue
                bulk[str(name)] = (
                    bool(item.get('ok', False)),
                    str(item.get('detail', '')),
                    item.get('staleAfterSec'),
                )
            if bulk:
                self._manager.bulk_update(bulk)
        elif 'check' in payload:
            self._manager.update(
                str(payload.get('check', 'unknown')),
                bool(payload.get('ok', False)),
                str(payload.get('detail', '')),
                payload.get('staleAfterSec'),
            )
        mode = payload.get('mode')
        if mode:
            current = self._manager.snapshot()
            self._manager.set_mode(str(mode))
            self._manager.set_semantics(
                controller_mode=str(payload.get('controllerMode', current.controller_mode)),
                runtime_phase=str(payload.get('runtimePhase', current.runtime_phase)),
                task_stage=str(payload.get('taskStage', current.task_stage)),
            )

    def _on_hardware(self, msg: HardwareState) -> None:
        try:
            raw_status = json.loads(str(msg.raw_status or '{}'))
        except Exception:
            raw_status = {}
        hardware_present = bool(raw_status.get('hardwarePresent', raw_status.get('online', bool(msg.stm32_online))))
        transport_mode = str(raw_status.get('transportMode', 'real' if hardware_present else 'unavailable'))
        authoritative = bool(raw_status.get('hardwareAuthoritative', raw_status.get('authoritative', False)))
        controllable = bool(raw_status.get('hardwareControllable', hardware_present and authoritative))
        simulated_fallback = bool(raw_status.get('simulatedFallback', False))
        stale = bool(raw_status.get('state_stale', False))
        if not hardware_present:
            detail = 'hardware_offline'
            ok = False
        elif stale:
            detail = 'hardware_stale'
            ok = False
        elif simulated_fallback:
            detail = 'simulated_fallback'
            ok = False
        elif transport_mode == 'simulated' and not authoritative:
            detail = 'simulated_transport'
            ok = False
        elif transport_mode == 'simulated' and authoritative and controllable:
            detail = 'hardware_ready_simulated'
            ok = True
        elif not authoritative:
            detail = 'hardware_not_authoritative'
            ok = False
        elif not controllable:
            detail = 'hardware_uncontrollable'
            ok = False
        elif bool(msg.estop_pressed) or bool(msg.limit_triggered):
            detail = 'hardware_blocked'
            ok = False
        elif int(msg.hardware_fault_code) != 0:
            detail = 'hardware_fault'
            ok = False
        else:
            detail = 'hardware_ready'
            ok = True
        self._manager.update('hardware_bridge', ok, detail, 1.5)

    def _apply_calibration_payload(self, payload: dict[str, object]) -> None:
        profile = payload.get('profile', {}) if isinstance(payload, dict) else {}
        ok = bool(profile)
        detail = str(profile.get('version', 'missing')) if isinstance(profile, dict) and ok else 'missing'
        self._manager.update('calibration', ok, detail, None)

    def _on_calibration(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except Exception:
            self._manager.update('calibration', False, 'parse_error', None)
            return
        if not isinstance(payload, dict):
            self._manager.update('calibration', False, 'parse_error', None)
            return
        self._apply_calibration_payload(payload)

    def _on_calibration_typed(self, msg: CalibrationProfileMsg) -> None:
        payload = parse_calibration_profile_message(msg)
        if not payload:
            self._manager.update('calibration', False, 'parse_error', None)
            return
        self._apply_calibration_payload(payload)

    def _on_profiles(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            ok = bool(payload.get('task_profile'))
            detail = 'profiles_loaded' if ok else 'profiles_missing'
        except Exception:
            ok = False
            detail = 'parse_error'
        self._manager.update('profiles', ok, detail, None)

    def _on_target(self, msg: TargetInfo) -> None:
        """Consume the authoritative primary-target stream for compatibility observers.

        Args:
            msg: Primary target message.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        stale_after = float(self.get_parameter('camera_stale_sec').value)
        if bool(msg.is_valid):
            self._manager.update('target_available', True, 'target_available', stale_after)

    def _publish(self) -> None:
        if not self.runtime_active:
            return
        snapshot = self._manager.snapshot()
        payload = snapshot.as_dict()
        self._pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
        if self._typed_pub is not None:
            self._typed_pub.publish(build_readiness_state_message(payload))
        self._bringup_pub.publish(
            String(
                data=json.dumps(
                    {
                        'ready': snapshot.mode_ready,
                        'runtimeHealthy': snapshot.runtime_healthy,
                        'missing': snapshot.missing(),
                        'runtimeMissing': snapshot.runtime_missing(),
                        'mode': snapshot.mode,
                        'controllerMode': snapshot.controller_mode,
                        'runtimePhase': snapshot.runtime_phase,
                        'taskStage': snapshot.task_stage,
                        'commandSummary': snapshot.command_summary(),
                    },
                    ensure_ascii=False,
                )
            )
        )


def main(args=None) -> None:  # pragma: no cover
    if rclpy is None:
        raise RuntimeError('rclpy unavailable')
    lifecycle_main(ReadinessManagerNode, args=args)
