# Deprecation Matrix

| Package / Layer | Status | Retained Because | Replacement | Removal Condition |
| --- | --- | --- | --- | --- |
| `arm_task_manager` | deprecated | Legacy entrypoints may still import historical orchestration symbols | `arm_task_orchestrator` | Remove after no active imports remain in tests, launch files, or operator tooling |
| `arm_motion_bridge` | deprecated | Compatibility for historical motion bridge references | `arm_motion_planner` + `arm_motion_executor` | Remove after no runtime/launch path references remain |
| `arm_vision` | deprecated | Historical perception package alias | `arm_camera_driver` + `arm_perception` | Remove after compatibility topics and imports are fully retired |

## Hard rule

New runtime features must not add imports or launch references back into deprecated packages.

## Deprecated public endpoint migration

Deprecated packages no longer own canonical `/arm/*` public service/action names. Their retained compatibility endpoints are namespaced under `/arm/compat/*` to avoid repo-level ownership collisions with the active stack.

| Deprecated provider | Historical canonical endpoint | Compatibility endpoint | Canonical replacement owner |
| --- | --- | --- | --- |
| `arm_task_manager` | `/arm/start_task` | `/arm/compat/start_task` | `arm_task_orchestrator` |
| `arm_task_manager` | `/arm/reset_fault` | `/arm/compat/reset_fault` | `arm_task_orchestrator` |
| `arm_task_manager` | `/arm/stop_task` | `/arm/compat/stop_task` | `arm_task_orchestrator` |
| `arm_task_manager` | `/arm/home` | `/arm/compat/home` | `arm_task_orchestrator` |
| `arm_task_manager` | `/arm/pick_place_task` | `/arm/compat/pick_place_task` | `arm_task_orchestrator` |
| `arm_motion_bridge` | `/arm/pick_place_task` | `/arm/compat/pick_place_task` | `arm_task_orchestrator` + `arm_motion_planner`/`arm_motion_executor` |

Migration rule:
- New tooling, docs, launch files, and tests must use canonical active-stack owners only.
- Historical compatibility tooling must call `/arm/compat/*` explicitly and must not assume deprecated packages still own `/arm/*`.
