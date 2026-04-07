## Validation lanes

- Repository validation lane: Linux + Python 3.10+ + Node 22.x + npm 10.9.2，允许在无 ROS2 环境执行仓库级单元/契约/打包门禁。
- Target runtime lane: Ubuntu 22.04 + ROS2 Humble + Python 3.10.x，用于最终 build/launch/dispatcher/HIL 签收。

# Validation Report

## Repository validation commands

```bash
make verify
```

`make verify` 会顺序执行 backend-active / gateway / frontend / frontend-build / audit，并把每一步日志写入 `artifacts/repository_validation/*.log`。
`make test-backend` 现已恢复为完整后端仓库级入口，`make test-backend-active` 则保留为正式 active runtime lane。

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
