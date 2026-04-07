# Delivery Round 2 Addendum

## Closed items

### P0-3 `TaskOrchestratorNode` slimming
- Added `arm_task_orchestrator/runtime.py`
- Introduced `TaskRuntimeState`, `RuntimeHooks`, `TaskRuntimeEngine`
- Moved queue progression, stop/fault handling, dispatch, and verify progression out of the ROS node adapter
- `TaskOrchestratorNode` now primarily owns ROS publishers/subscribers/services/actions and delegates runtime progression to the engine
- Fixed task-profile reload path to rebuild the pure application stack instead of updating only partial members

### P1-2 end-to-end error envelope
- Added `arm_backend_common/event_envelope.py`
- `TaskEvent.message` and `FaultReport.message` can now carry structured metadata without breaking existing ROS message contracts
- Gateway log mapping now decodes requestId / correlationId / stage / errorCode / operatorActionable / payload when present

### P1-5 facade/library-shape vs node adapter layout
- Added `core/` and `node_adapter/` packages for:
  - `arm_camera_driver`
  - `arm_perception`
  - `arm_scene_manager`
  - `arm_grasp_planner`
- Root package exports remain backward compatible
- Updated setuptools package discovery to include nested subpackages

### P2 runtime supervision and CI evidence chain
- Added `arm_lifecycle_manager/runtime_supervisor_node.py`
- Added optional bringup launch arg `enable_lifecycle_supervisor`
- Registered `runtime_supervisor_node` entrypoint
- Enhanced GitHub Actions CI with:
  - Python pip cache
  - fixed Node version `22.16.0`
  - frontend/backend/ROS build logs as uploaded artifacts
  - frontend dist upload
  - ROS colcon and smoke logs upload

## Remaining limitation

The repository now has explicit runtime supervision, but it still does **not** convert the runtime-core nodes into true ROS managed lifecycle nodes. Achieving a full lifecycle state-machine rollout would require changing node implementations from plain `rclpy.Node` semantics to lifecycle-aware node semantics across multiple packages. That exceeds a low-risk compatibility patch.
