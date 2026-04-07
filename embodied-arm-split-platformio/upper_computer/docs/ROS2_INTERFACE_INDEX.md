# ROS 2 Interface Index

> Generated from `arm_common/topic_names.py`, `service_names.py`, `action_names.py`, and `arm_bringup/launch_factory.py`.

## Authoritative topics
- `/arm/bringup/status`
- `/arm/bringup/status_typed`
- `/arm/calibration/profile_typed`
- `/arm/camera/frame_summary`
- `/arm/camera/health`
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
- `/arm/diagnostics/health`
- `/arm/readiness/state`
- `/arm/task/status`
- `/arm/vision/targets`

## Internal control topics
- `/arm/internal/hardware_cmd`
- `/arm/internal/stop_cmd`

## Topic semantics

- `/arm/bringup/status`: JSON compatibility bringup / lifecycle summary
- `/arm/bringup/status_typed`: typed shadow bringup / lifecycle summary
- `/arm/camera/frame_summary`: camera runtime freshness / source summary used by perception runtime
- `/arm/camera/health`: camera health projection for diagnostics / readiness
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
- `official_runtime` -> `sim`

