# ROS 2 Interface Index

> Generated from `arm_common/topic_names.py`, `service_names.py`, `action_names.py`, and `arm_bringup/launch_factory.py`.

## Authoritative topics
- `/arm/bringup/status`
- `/arm/bringup/status_typed`
- `/arm/calibration/profile_typed`
- `/arm/camera/frame_summary`
- `/arm/camera/health`
- `/arm/camera/image_raw`
- `/arm/camera/camera_info`
- `/arm/diagnostics/summary_typed`
- `/arm/fault/report`
- `/arm/hardware/state`
- `/arm/log/event`
- `/arm/readiness/state_typed`
- `/arm/system/state`
- `/arm/task/status_typed`
- `/arm/vision/summary`
- `/arm/vision/target`
- `/arm/vision/targets_typed`

## Compatibility / aggregation topics
- `/arm/calibration/profile`
- `/arm/camera/image_raw_compat`
- `/arm/diagnostics/health`
- `/arm/readiness/state`
- `/arm/task/status`
- `/arm/vision/targets`

## Internal control topics
- `/arm/internal/execution_status`
- `/arm/internal/hardware_cmd`
- `/arm/internal/ros2_control_cmd`
- `/arm/internal/stop_cmd`

## Topic semantics

- `/arm/bringup/status`: JSON compatibility bringup / lifecycle summary
- `/arm/bringup/status_typed`: typed shadow bringup / lifecycle summary
- `/arm/camera/frame_summary`: camera runtime freshness / source summary used by perception runtime
- `/arm/camera/health`: camera health projection for diagnostics / readiness
- `/arm/camera/image_raw_compat`: legacy JSON frame ingress kept only for migration compatibility
- `/arm/camera/image_raw`: standard sensor_msgs/Image ingress used by topic-backed camera runtime lanes
- `/arm/camera/camera_info`: camera intrinsic metadata paired with standard image ingress
- `/arm/internal/execution_status`: internal execution-status stream used for task/executor correlation
- `/arm/internal/ros2_control_cmd`: internal ros2_control command metadata emitted by motion executor
- `/arm/vision/summary`: perception runtime health / freshness summary
- `/arm/vision/target`: authoritative primary target contract used by readiness and command pipeline
- `/arm/vision/targets`: compatibility multi-target summary for UI aggregation and transitional consumers

## Services
- `/arm/activate_calibration`
- `/calibration_manager_node/reload`
- `/arm/home`
- `/arm/reset_fault`
- `/arm/set_mode`
- `/arm/start_task`
- `/arm/stop`
- `/arm/stop_task`

## Actions
- `/arm/home_sequence`
- `/arm/homing`
- `/arm/manual_servo`
- `/arm/pick_place_task`
- `/arm/recover`

## Package ownership
- execution: `arm_motion_executor`
- hardware io: `arm_hardware_bridge`
- lifecycle supervision: `arm_lifecycle_manager`
- perception input: `arm_camera_driver`
- perception processing: `arm_perception`
- planning: `arm_motion_planner`
- readiness: `arm_readiness_manager`
- safety: `arm_safety_supervisor`
- task orchestration: `arm_task_orchestrator`

## Runtime lanes
- `authoritative_runtime` -> `sim_authoritative`
- `full_demo` -> `full_demo_preview`
- `full_demo_validated` -> `full_demo_authoritative`
- `hw` -> `hw_preview`
- `hybrid` -> `hybrid_preview`
- `live` -> `real_validated_live`
- `official_runtime` -> `sim_preview`
- `real` -> `real_preview`
- `real_authoritative` -> `real_candidate`
- `real_authoritative_live` -> `real_validated_live`
- `real_validated` -> `real_candidate`
- `sim` -> `sim_preview`
- `sim_perception_realistic` -> `sim_perception_preview`
- `sim_validated` -> `sim_authoritative`
- `validated_live` -> `real_validated_live`

