## Validation lanes

- Repository validation lane: Linux + Python 3.10+ + Node 22.x + npm 10.9.2，允许在无 ROS2 环境执行仓库级单元/契约/打包门禁。
- Target runtime lane: Ubuntu 22.04 + ROS2 Humble + Python 3.10.x，用于最终 build/launch/dispatcher/HIL 签收。

# Validation Report

## Repository validation commands

```bash
make verify        # repository gate（默认完整仓库门禁）
make verify-fast   # 开发快反馈门禁
```

`make verify` / `make verify-repo` 现在会顺序执行 `backend-full -> backend-active -> active-profile-consistency -> interface-mirror-drift -> contract-artifacts -> runtime-contracts -> gateway -> frontend-deps -> frontend-typecheck-app -> frontend-typecheck-test -> frontend-unit -> frontend-build -> frontend-e2e -> audit`，并把日志写入 `artifacts/repository_validation/repo/*.log 与 artifacts/repository_validation/repo/verification_summary.json`。

`make verify-fast` 保留原来的快反馈语义，但名称被显式收紧为 fast lane；它不会替代完整仓库门禁，日志写入 `artifacts/repository_validation/fast/*.log`。

`make test-backend` 是完整后端回归入口，`make test-backend-active` 是 active runtime lane，二者都必须保留，避免出现 active lane 通过但完整后端回归已漂移的假绿状态。

如需拆分执行，仍可单独运行：

```bash
make test-backend
make test-backend-active
make test-gateway
make test-frontend
make frontend-build
python scripts/final_audit.py
```

## Semantic validation focus

当前仓库级验证重点覆盖：

- layered readiness contract (`runtimeHealthy` / `modeReady` / `commandPolicies`)
- authoritative-vs-simulated hardware semantics
- gateway fail-closed bootstrap behavior
- frontend runtime/mode/command display layering

仓库级通过不等于目标环境真机闭环通过。

## Target-lane promotion assets

`make ros-target-validate` 现在无论成功还是失败都会产出：

- `artifacts/target_env_report.json`
- `artifacts/release_gates/target_runtime_gate.json`（失败步骤会被标记为 `failed` 或 `blocked`）
- `artifacts/hil/hil_checklist.json`

## Runtime-state and observability paths

- 默认 Gateway runtime state: `${XDG_STATE_HOME:-~/.local/state}/embodied-arm/gateway_data`
- 默认 observability sink: `${XDG_STATE_HOME:-~/.local/state}/embodied-arm/gateway_observability/*.jsonl`
- 兼容覆盖仍支持 `EMBODIED_ARM_GATEWAY_DATA_DIR` 与 `EMBODIED_ARM_OBSERVABILITY_DIR`
- `artifacts/` 与 `gateway_data/` 仍会被 release packaging 排除

## Practical conclusion

- 仓库级验证可以在无 ROS2 环境完成。
- 真实 `colcon build`、`runtime_real.launch`、dispatcher round-trip 与 HIL，仍必须在 Ubuntu 22.04 + ROS2 Humble 目标环境执行，不应把仓库级通过误写成目标环境闭环通过。

```bash
make target-env-bootstrap
```

```bash
make ros-target-validate-docker
```

Target validation now records `negative_path_subset` separately from `ros_smoke`, and HIL remains a distinct blocking gate.

- Runtime contract generation now emits both `docs/generated/runtime_contract_manifest.json` and `docs/generated/runtime_contract_schema.json`; both are part of contract drift validation.
- Public task templates are expected to expose `graphKey + taskGraph`; contract validation treats missing task-graph descriptors as a release-blocking drift.
- Release packaging validation must confirm that experimental / archived packages (`arm_hmi`, `arm_task_manager`, `arm_motion_bridge`, `arm_vision`) are excluded from the curated source zip.

## Active-profile quarantine discipline

- `backend/embodied_arm_ws/active_profile_quarantine.json` 是 active lane 忽略测试的唯一台账。
- `pytest-active.ini` 中的 `--ignore` 列表必须与该台账一一对应。
- `python scripts/check_active_profile_consistency.py` 现在会同时校验：
  - active pythonpath 只暴露 runtime core + supervision 包
  - 忽略测试与 quarantine 台账一致
  - 每个忽略项都带 owner / category / reason / expires

- `backend/embodied_arm_ws/src/arm_bringup/config/validated_live_evidence.yaml` is the machine-readable status file for target-runtime HIL and release-checklist evidence. Repository-level validation must not mark `validated_live` as promoted unless this file records `passed` for the required artifacts.
