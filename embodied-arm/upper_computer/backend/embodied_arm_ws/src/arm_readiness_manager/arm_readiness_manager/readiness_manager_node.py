from __future__ import annotations

import json

try:
    import rclpy
    from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
    from std_msgs.msg import String
    from arm_common import (
        MsgTypes,
        SrvTypes,
        TopicNames,
        ServiceNames,
        build_readiness_state_message,
        parse_calibration_profile_message,
    )
    CalibrationProfileMsg = MsgTypes.CalibrationProfileMsg
    HardwareState = MsgTypes.HardwareState
    ReadinessState = MsgTypes.ReadinessState
    TargetInfo = MsgTypes.TargetInfo
    SetMode = SrvTypes.SetMode
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
    SetMode = object

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

    class ServiceNames:
        SET_MODE = '/arm/set_mode'

from .readiness import ReadinessManager


class ReadinessManagerNode(ManagedLifecycleNode):
    """Aggregate authoritative runtime readiness checks and publish one snapshot."""

    def __init__(self) -> None:
        super().__init__('readiness_manager')
        self.declare_parameter('publish_period_sec', 0.5)
        self.declare_parameter('camera_stale_sec', 2.0)
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
        self.create_service(SetMode, ServiceNames.SET_MODE, self._handle_set_mode)
        self.create_timer(float(self.get_parameter('publish_period_sec').value), self._publish)
        self._manager.update('ros2', True, 'node_started')

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
            self._manager.set_mode(
                str(mode),
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

    def _handle_set_mode(self, request: SetMode.Request, response: SetMode.Response) -> SetMode.Response:
        if not self.runtime_active:
            response.success = False
            response.message = 'readiness manager inactive'
            return response
        mode = str(request.mode or 'idle').strip().lower()
        current = self._manager.snapshot()
        self._manager.set_mode(mode, controller_mode=mode, runtime_phase=current.runtime_phase, task_stage=current.task_stage)
        response.success = True
        response.message = f'mode set to {mode}'
        return response

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
