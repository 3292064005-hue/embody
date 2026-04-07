cmake_minimum_required(VERSION 3.8)
project(arm_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(action_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)

set(MSG_FILES
  "msg/SystemState.msg"
  "msg/HardwareState.msg"
  "msg/TargetInfo.msg"
  "msg/Target.msg"
  "msg/TargetArray.msg"
  "msg/TaskEvent.msg"
  "msg/EventLog.msg"
  "msg/FaultReport.msg"
  "msg/DiagnosticsSummary.msg"
  "msg/CalibrationProfileMsg.msg"
  "msg/BringupStatus.msg"
  "msg/ReadinessState.msg"
  "msg/TaskStatus.msg"
  "msg/GraspCandidate.msg"
)

set(SRV_FILES
  "srv/StartTask.srv"
  "srv/ResetFault.srv"
  "srv/StopTask.srv"
  "srv/Stop.srv"
  "srv/HomeArm.srv"
  "srv/ActivateCalibrationVersion.srv"
  "srv/ReloadCalibration.srv"
  "srv/SetMode.srv"
  "srv/CaptureCalibrationFrame.srv"
)

set(ACTION_FILES
  "action/PickPlaceTask.action"
  "action/ManualServo.action"
  "action/HomeSequence.action"
  "action/Homing.action"
  "action/Recover.action"
)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${MSG_FILES}
  ${SRV_FILES}
  ${ACTION_FILES}
  DEPENDENCIES std_msgs builtin_interfaces geometry_msgs action_msgs sensor_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
