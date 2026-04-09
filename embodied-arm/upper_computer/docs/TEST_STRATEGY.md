# Test Strategy

## Backend
- pure unit tests under `backend/embodied_arm_ws/tests`
- launch integrity tests for bringup launch files
- semantic readiness / runtime contract tests
- split-stack regression tests
- full-repository backend lane via `make test-backend`
- active-stack constrained profile via `backend/embodied_arm_ws/pytest-active.ini`

## Gateway
- FastAPI REST contract tests
- WebSocket snapshot and authorization tests
- readiness / hardware authority semantic tests
- observability sink tests covering async flush and failing sinks
- configuration guard tests (for example fail-closed CORS combinations)

## Frontend
- pure domain and command-bus tests via Vitest
- readiness/safety store tests
- build/typecheck gates
- Playwright end-to-end smoke for dashboard bootstrap semantic fields and top-status runtime/mode/command layering

## Runtime semantic smoke

Semantic smoke must validate more than process startup:

- authoritative readiness payload is present
- camera/perception/target chain is represented in runtime contracts
- fail-closed hardware semantics survive into gateway/UI payloads
- maintenance/manual command gating remains aligned with readiness rules

## Hardware-in-loop
- home
- fault reset
- gripper open/close
- jog/servo
- task start/stop/verify

## P0 / P1 traceability

See `docs/P0_P1_TRACEABILITY.md` for the explicit mapping between approved P0/P1 items and the executable test set.

- contract-artifact sync check (`scripts/generate_contract_artifacts.py --check`) guards the generated runtime manifest and markdown summary against drift.

## Target negative-path subset
- hardware bridge unavailable
- readiness blocked propagation
- safety stop propagation
