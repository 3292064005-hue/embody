# Release Checklist

## Repository gates
- [ ] `make verify` green
- [ ] `make repo-gate` green (alias of repository verification)
- [ ] `artifacts/repository_validation/repo/*.log 与 artifacts/repository_validation/repo/verification_summary.json` generated
- [ ] if needed, each split repository gate can still be run individually (`make test-backend`, `make test-backend-active`, `make test-gateway`, `make test-frontend`, `make frontend-build`, `python scripts/final_audit.py`)

## Semantic contracts
- [ ] `controllerMode / runtimePhase / taskStage` exposed in gateway/public snapshots
- [ ] legacy aliases (`mode / operatorMode / currentStage`) preserved for compatibility
- [ ] readiness and diagnostics payloads updated accordingly
- [ ] servo-cartesian endpoint is wired through gateway validation, dispatcher mapping, and transport feedback closure

## Target-runtime promotion assets
- [ ] `artifacts/target_env_report.json` generated
- [ ] `artifacts/release_gates/target_runtime_gate.json` generated
- [ ] `artifacts/release_gates/release_evidence.json` generated
- [ ] `artifacts/hil/hil_checklist.json` generated
- [ ] `make target-gate` executed on Ubuntu 22.04 + ROS2 Humble
- [ ] report explicitly records `repoGate / targetGate / hilGate` status
- [ ] report explicitly records `evidenceLevels(L1/L2/L3/L4)` so claims do not exceed validation strength

## Packaging hygiene
- [ ] runtime mutable state lives outside source tree by default
- [ ] source-tree `gateway_data/` excluded from release archives
- [ ] source-tree `artifacts/` excluded from release archives except the packager-written `artifacts/split_release_manifest.json`
- [ ] zip artifact created from clean tree
- [ ] `artifacts/split_release_manifest.json` reviewed against the generated archive
- [ ] README / VALIDATION / gateway docs synchronized

- [ ] negative-path subset gate is recorded in `artifacts/release_gates/target_runtime_gate.json`
- [ ] `official_runtime.launch.py` is documented only as a compatibility alias to `runtime_sim.launch.py`
