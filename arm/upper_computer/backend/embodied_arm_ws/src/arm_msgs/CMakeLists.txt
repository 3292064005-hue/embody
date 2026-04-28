cmake_minimum_required(VERSION 3.8)
project(arm_msgs)

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
  "msg/TaskEvent.msg"
  "msg/FaultReport.msg"
  "msg/DiagnosticsSummary.msg"
  "msg/CalibrationProfileMsg.msg"
  "msg/BringupStatus.msg"
  "msg/ReadinessState.msg"
  "msg/TaskStatus.msg"
  "msg/GraspCandidate.msg"
  "msg/EventLog.msg"
  "msg/TargetArray.msg"
  "msg/Target.msg"
)

set(SRV_FILES
  "srv/StartTask.srv"
  "srv/ResetFault.srv"
  "srv/StopTask.srv"
  "srv/HomeArm.srv"
  "srv/ActivateCalibrationVersion.srv"
  "srv/ReloadCalibration.srv"
  "srv/SetMode.srv"
  "srv/CaptureCalibrationFrame.srv"
  "srv/RuntimeSceneSnapshot.srv"
  "srv/RuntimeGraspPlan.srv"
  "srv/Stop.srv"
)

set(ACTION_FILES
  "action/PickPlaceTask.action"
  "action/ManualServo.action"
  "action/HomeSequence.action"
  "action/Recover.action"
  "action/Homing.action"
)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${MSG_FILES}
  ${SRV_FILES}
  ${ACTION_FILES}
  DEPENDENCIES std_msgs builtin_interfaces geometry_msgs action_msgs sensor_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
