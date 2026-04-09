# Architecture Freeze

## Official runtime chain

- HMI: `frontend/`
- Gateway BFF: `gateway/`
- ROS2 split stack: `arm_readiness_manager -> arm_safety_supervisor -> arm_task_orchestrator -> arm_motion_planner -> arm_motion_executor -> arm_hardware_bridge`
- Vision: `arm_camera_driver` + `arm_perception`
- Calibration/Profile: `arm_calibration`, `arm_profiles`
- Diagnostics/Logging: `arm_diagnostics`, `arm_logger`

## Frozen design rules

1. Frontend never talks to ROS2 directly.
2. Gateway is the only HMI-facing API surface.
3. New backend behavior must land in split-stack packages, not in deprecated legacy packages.
4. Pick/place task orchestration belongs to `arm_task_orchestrator`.
5. Motion planning belongs to `arm_motion_planner` and motion execution belongs to `arm_motion_executor`.
6. Device communication belongs to `arm_hardware_bridge`.
7. Readiness is the execution gate; diagnostics is the health summary; they are not interchangeable.
