# Deprecation Matrix

| Package / Layer | Status | Retained Because | Replacement | Removal Condition |
| --- | --- | --- | --- | --- |
| `arm_task_manager` | deprecated | Legacy entrypoints may still import historical orchestration symbols | `arm_task_orchestrator` | Remove after no active imports remain in tests, launch files, or operator tooling |
| `arm_motion_bridge` | deprecated | Compatibility for historical motion bridge references | `arm_motion_planner` + `arm_motion_executor` | Remove after no runtime/launch path references remain |
| `arm_vision` | deprecated | Historical perception package alias | `arm_camera_driver` + `arm_perception` | Remove after compatibility topics and imports are fully retired |

## Hard rule

New runtime features must not add imports or launch references back into deprecated packages.
