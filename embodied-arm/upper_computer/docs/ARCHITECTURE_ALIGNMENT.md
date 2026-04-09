# Architecture Alignment Snapshot

This snapshot records how the repository is currently aligned with the approved class-level / node-level blueprint.

## Closed gaps in the current revision

- Public semantic contract separates `controllerMode`, `runtimePhase`, and `taskStage` while keeping legacy aliases.
- Readiness now exposes layered semantics: `runtimeHealthy`, `modeReady`, and `commandPolicies` instead of overloading one boolean.
- Camera runtime publishes explicit frame/health summaries and perception runtime consumes that stream before publishing authoritative target output.
- Readiness now consumes authoritative hardware authority semantics (`transportMode`, `authoritative`, simulated fallback flags) instead of treating generic online state as sufficient.
- STM32 transport defaults to fail-closed in target runtime profiles; simulated fallback requires explicit enablement.
- Gateway and HMI now surface hardware simulation / fallback state instead of presenting it as normal runtime readiness.
- Lifecycle management now reports layered bringup progress (`currentLayer`, `blockingNode`, `retryCount`, `terminalFaultReason`) and continues monitoring managed nodes after autostart so stale/inactive nodes surface as runtime blockers instead of remaining silent.
- Gateway CORS policy moved to explicit environment configuration with production-safe credential/origin validation.

## Still true after this pass

- The repository remains a staged transition rather than a final clean-sheet rewrite; legacy packages still exist for compatibility and regression containment.
- Several blueprint packages are still architecture-convergence facades / helper modules, not full production runtime implementations.
- A full ROS2 build-and-launch proof remains blocked in non-target environments without `colcon`.
- `/arm/vision/targets` remains a compatibility topic; the source of truth is `/arm/vision/target`.

## Runtime layering after the current pass

- Runtime Core: `arm_profiles`, `arm_calibration`, `arm_hardware_bridge`, `arm_esp32_gateway`, `arm_readiness_manager`, `arm_safety_supervisor`, `arm_camera_driver`, `arm_perception`, `arm_scene_manager`, `arm_grasp_planner`, `arm_motion_planner`, `arm_motion_executor`, `arm_task_orchestrator`, `arm_bt_runtime`, `arm_bt_nodes`, `arm_diagnostics`, `arm_logger`
- Runtime supervision: `arm_lifecycle_manager`
- Compatibility: `arm_task_manager`, `arm_motion_bridge`, `arm_vision`, legacy target summary consumers
- Experimental: `arm_hmi`
- Package support matrix: see `docs/PACKAGE_SUPPORT_MATRIX.md` for the enforced active-lane / compatibility / experimental split

## Primary architectural rules now enforced in-code

- authoritative runtime health must come from real subsystem activity rather than process existence
- simulated hardware must not silently masquerade as real hardware in target-runtime profiles
- readiness snapshots must distinguish runtime health, mode readiness, and per-command gating
- UI readiness indicators must expose simulation / degraded / blocked reasons explicitly
