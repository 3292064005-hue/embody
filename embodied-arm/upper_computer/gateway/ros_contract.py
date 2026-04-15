from __future__ import annotations

try:
    from arm_common import ActionNames, ActionTypes, MsgTypes, SrvTypes, TopicNames, ServiceNames
    BringupStatus = MsgTypes.BringupStatus
    CalibrationProfileMsg = MsgTypes.CalibrationProfileMsg
    DiagnosticsSummary = MsgTypes.DiagnosticsSummary
    HardwareState = MsgTypes.HardwareState
    ReadinessState = MsgTypes.ReadinessState
    SystemState = MsgTypes.SystemState
    TargetArray = MsgTypes.TargetArray
    TargetInfo = MsgTypes.TargetInfo
    TaskEvent = MsgTypes.TaskEvent
    TaskStatus = MsgTypes.TaskStatus
    HomeArm = SrvTypes.HomeArm
    ResetFault = SrvTypes.ResetFault
    SetMode = SrvTypes.SetMode
    StartTask = SrvTypes.StartTask
    StopTask = SrvTypes.StopTask
    ActivateCalibrationVersion = SrvTypes.ActivateCalibrationVersion
    PickPlaceTask = ActionTypes.PickPlaceTask
    Homing = ActionTypes.Homing
    Recover = ActionTypes.Recover
except Exception:  # pragma: no cover - used outside the test harness
    BringupStatus = CalibrationProfileMsg = DiagnosticsSummary = HardwareState = ReadinessState = SystemState = TargetArray = TargetInfo = TaskEvent = TaskStatus = object
    HomeArm = ResetFault = SetMode = StartTask = StopTask = ActivateCalibrationVersion = object
    PickPlaceTask = Homing = Recover = object

    class TopicNames:
        SYSTEM_STATE = '/arm/system/state'
        HARDWARE_STATE = '/arm/hardware/state'
        VISION_TARGET = '/arm/vision/target'
        LOG_EVENT = '/arm/log/event'
        INTERNAL_HARDWARE_CMD = '/arm/internal/hardware_cmd'
        TASK_STATUS = '/arm/task/status'
        TASK_STATUS_TYPED = '/arm/task/status_typed'
        DIAGNOSTICS_HEALTH = '/arm/diagnostics/health'
        DIAGNOSTICS_SUMMARY_TYPED = '/arm/diagnostics/summary_typed'
        CALIBRATION_PROFILE = '/arm/calibration/profile'
        CALIBRATION_PROFILE_TYPED = '/arm/calibration/profile_typed'
        READINESS_STATE = '/arm/readiness/state'
        READINESS_STATE_TYPED = '/arm/readiness/state_typed'
        BRINGUP_STATUS = '/arm/bringup/status'
        BRINGUP_STATUS_TYPED = '/arm/bringup/status_typed'
        VISION_TARGETS = '/arm/vision/targets'
        VISION_TARGETS_TYPED = '/arm/vision/targets_typed'
        VOICE_EVENTS = '/arm/voice/events'

    class ServiceNames:
        HOME = '/arm/home'
        RESET_FAULT = '/arm/reset_fault'
        STOP = '/arm/stop'
        STOP_TASK = '/arm/stop_task'
        SET_MODE = '/arm/set_mode'
        START_TASK = '/arm/start_task'
        CALIBRATION_MANAGER_RELOAD = '/calibration_manager_node/reload'
        ACTIVATE_CALIBRATION = '/arm/activate_calibration'

    class ActionNames:
        PICK_PLACE_TASK = '/arm/pick_place_task'
        HOMING = '/arm/homing'
        RECOVER = '/arm/recover'

__all__ = [
    'BringupStatus',
    'CalibrationProfileMsg', 'DiagnosticsSummary', 'HardwareState', 'ReadinessState', 'SystemState', 'TargetArray', 'TargetInfo', 'TaskEvent', 'TaskStatus',
    'HomeArm', 'ResetFault', 'SetMode', 'StartTask', 'StopTask', 'ActivateCalibrationVersion',
    'PickPlaceTask', 'Homing', 'Recover',
    'TopicNames', 'ServiceNames', 'ActionNames',
]
