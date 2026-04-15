# Contract Index

Authoritative contract artifacts are generated from backend readiness contracts plus ROS interface definitions. Do not hand-edit generated interface lists.

## Generated artifacts
- `generated/runtime_contract_manifest.json`
- `generated/runtime_contract_schema.json`
- `generated/runtime_contract_summary.md`
- `generated/runtime_acceptance_matrix.md`
- `ROS2_INTERFACE_INDEX.md`

## Source of truth
- `backend/embodied_arm_ws/src/arm_common/arm_common/topic_names.py`
- `backend/embodied_arm_ws/src/arm_common/arm_common/service_names.py`
- `backend/embodied_arm_ws/src/arm_common/arm_common/action_names.py`
- `backend/embodied_arm_ws/src/arm_bringup/config/runtime_authority.yaml`
- `backend/embodied_arm_ws/src/arm_bringup/arm_bringup/launch_factory.py` (consumes generated lane projection only)
- `backend/embodied_arm_ws/src/arm_readiness_manager/arm_readiness_manager/contract_defs.py`
- `backend/embodied_arm_ws/src/arm_bringup/config/task_capability_manifest.yaml`
- `gateway/generated/runtime_contract.py`
- `frontend/src/generated/runtimeContract.ts`

