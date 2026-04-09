# P0 / P1 Active Release Traceability Matrix

This matrix maps the approved P0 / P1 checklist to **active runtime** verification evidence only.
Compatibility-only regression suites are tracked separately in `docs/COMPATIBILITY_REGRESSION_EVIDENCE.md` and must not be cited as active release proof.

## P0

- arm interfaces / mirror contract tests
  - `backend/embodied_arm_ws/tests/test_interface_manifest_sync.py`
  - `backend/embodied_arm_ws/tests/test_interface_mirror_sync.py`
  - `backend/embodied_arm_ws/tests/test_interface_mirror_check_gate.py`
- runtime lane truthfulness tests
  - `backend/embodied_arm_ws/tests/test_runtime_lane_truthfulness.py`
  - `backend/embodied_arm_ws/tests/test_runtime_semantic_contracts.py`
  - `backend/embodied_arm_ws/tests/test_planning_truthfulness.py`
- safety / protocol / readiness tests
  - `backend/embodied_arm_ws/tests/test_safety_policy.py`
  - `backend/embodied_arm_ws/tests/test_protocol.py`
  - `backend/embodied_arm_ws/tests/test_camera_health_contract.py`
- planner / executor / provider boundary tests
  - `backend/embodied_arm_ws/tests/test_planner_executor_runtime_contracts.py`
  - `backend/embodied_arm_ws/tests/test_provider_boundary_closure.py`
  - `backend/embodied_arm_ws/tests/test_scene_manager_runtime_contract.py`
  - `backend/embodied_arm_ws/tests/test_grasp_planner_runtime_contract.py`
- gateway contract tests
  - `gateway/tests/test_server.py`
  - `gateway/tests/test_runtime_contracts.py`
  - `gateway/tests/test_recover_and_boundary.py`
- frontend store / semantics tests
  - `frontend/src/services/commands/commandBus.test.ts`
  - `frontend/src/domain/safety/guards.test.ts`
  - `frontend/src/stores/safety.test.ts`
  - `frontend/src/models/runtimeFeatures.test.ts`
  - `frontend/src/components/system/statusSemantics.test.ts`

## P1

- launch / lane layout tests
  - `backend/embodied_arm_ws/tests/test_launch_factory_contracts.py`
  - `backend/embodied_arm_ws/tests/test_launch_integrity.py`
  - `backend/embodied_arm_ws/tests/test_runtime_lane_semantics.py`
- camera → perception → HMI frame summary tests
  - `backend/embodied_arm_ws/tests/test_frame_publisher_summary.py`
  - `gateway/tests/test_hardware_camera_semantics.py`
- reset fault / recover / maintenance closure tests
  - `gateway/tests/test_recover_and_boundary.py`
  - `backend/embodied_arm_ws/tests/test_runtime_semantic_contracts.py`

## Validation commands

```bash
python scripts/check_active_profile_consistency.py
python scripts/sync_interface_mirror.py --check
python scripts/generate_contract_artifacts.py --check
cd backend/embodied_arm_ws && python -m pytest -q -c pytest-active.ini -p no:cacheprovider
cd ../.. && python -m pytest -q gateway/tests -p no:cacheprovider
cd frontend && npm run typecheck && npm run test:unit && npm run build
python scripts/final_audit.py
```
