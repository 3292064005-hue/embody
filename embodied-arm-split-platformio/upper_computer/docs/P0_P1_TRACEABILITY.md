# P0 / P1 Traceability Matrix

This matrix maps the approved P0 / P1 checklist to concrete repository tests and validation commands.

## P0

- arm_interfaces contract tests
  - `backend/embodied_arm_ws/tests/test_interface_manifest_sync.py`
  - `backend/embodied_arm_ws/tests/test_interface_mirror_sync.py`
  - `backend/embodied_arm_ws/tests/test_p0_p1_coverage.py::test_p0_interfaces_contract_files_exist`
- orchestrator state machine tests
  - `backend/embodied_arm_ws/tests/test_split_stack_logic.py`
  - `backend/embodied_arm_ws/tests/test_queue_and_reservation.py`
- safety fault latch / stop policy tests
  - `backend/embodied_arm_ws/tests/test_safety_policy.py`
- readiness aggregation tests
  - `backend/embodied_arm_ws/tests/test_readiness_and_planning.py`
- stm32 / protocol tests
  - `backend/embodied_arm_ws/tests/test_protocol.py`
- gateway contract tests
  - `gateway/tests/test_server.py`
  - `gateway/tests/test_runtime_contracts.py`
  - `gateway/tests/test_recover_and_boundary.py`
- frontend store + command guard tests
  - `frontend/src/services/commands/commandBus.test.ts`
  - `frontend/src/domain/safety/guards.test.ts`
  - `frontend/src/stores/safety.test.ts`

## P1

- launch smoke test
  - `backend/embodied_arm_ws/tests/test_launch_integrity.py`
  - `backend/embodied_arm_ws/tests/test_p0_p1_coverage.py::test_p1_launch_factory_smoke_across_modes`
- sim pick-place test
  - `backend/embodied_arm_ws/tests/test_p0_p1_coverage.py::test_p1_sim_pick_place_pipeline_smoke`
- cancel task test
  - `backend/embodied_arm_ws/tests/test_p0_p1_coverage.py::test_p1_cancel_task_marks_queued_task_canceled`
- reset fault and recover test
  - `gateway/tests/test_recover_and_boundary.py`
  - `backend/embodied_arm_ws/tests/test_p0_p1_coverage.py::test_p1_recover_action_clears_queue_and_returns_idle`

## Validation commands

```bash
python scripts/final_audit.py
pytest -q --disable-warnings
cd frontend && npm run typecheck && npm run test:unit && npm run build
```
