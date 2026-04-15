# gateway

该目录提供前后端整合所需的 HMI 网关层：

- 对前端暴露 REST 接口 `/api/*`
- 对前端暴露 WebSocket `/ws`
- 对后端订阅 ROS2 topic，并调用 ROS2 service
- 将 ROS2 的消息模型映射为前端 Vue HMI 所需的数据结构

## 启动

```bash
pip install -r gateway/requirements.txt -c gateway/constraints.txt
python -m gateway.main
```

默认端口：`8000`

## Environment contract

Validated baseline:

- Ubuntu 22.04 LTS
- Python 3.10
- Node.js: **22.x**
- npm: **10.9.2**
- ROS2 Humble (authoritative runtime path)

## Runtime semantics

Gateway 对外统一暴露：

- `controllerMode`
- `runtimePhase`
- `taskStage`
- `runtimeHealthy`
- `modeReady`
- `commandPolicies`
- `commandSummary`
- `authoritative`
- `simulated`

兼容期内仍保留：

- `mode`
- `operatorMode`

Gateway 仍对外保留 `operatorMode` 作为 `controllerMode` 的兼容别名；前端本地权限角色已统一使用 `operatorRole` 表示。
- `currentStage`
- `allReady`（兼容别名，语义等同于 `modeReady`）

## Hardware authority semantics

Gateway 不再把“在线”与“权威真机可控”混为一谈。对外数据中会区分：

- `sourceStm32Online`
- `sourceStm32Authoritative`
- `sourceStm32TransportMode`
- `sourceStm32Controllable`
- `sourceStm32Simulated`
- `sourceStm32SimulatedFallback`

默认 target-runtime 路径是 **fail-closed**：硬件不可用时，gateway 继续暴露阻断状态，而不是把 simulated fallback 伪装成真机在线。

## CORS configuration

CORS 由环境变量控制，而不是在生产默认值中硬编码全开放：

- `EMBODIED_ARM_CORS_ALLOW_ORIGINS`
- `EMBODIED_ARM_CORS_ALLOW_CREDENTIALS`
- `EMBODIED_ARM_CORS_ALLOW_METHODS`
- `EMBODIED_ARM_CORS_ALLOW_HEADERS`

当 `EMBODIED_ARM_CORS_ALLOW_CREDENTIALS=true` 时，不允许使用 `*` 作为 origin 白名单。

## Observability

Gateway 默认会把结构化 `logs` / `audits` 追加写入 `${XDG_STATE_HOME:-~/.local/state}/embodied-arm/gateway_observability/`。

可通过以下环境变量调整：

- `EMBODIED_ARM_STATE_ROOT`
- `EMBODIED_ARM_OBSERVABILITY_DIR`
- `EMBODIED_ARM_OBSERVABILITY_SYNC_MODE=strict`（强制同步刷盘）
- `EMBODIED_ARM_OBSERVABILITY_QUEUE_SIZE`

设置 `EMBODIED_ARM_OBSERVABILITY_DIR=off` 可关闭本地 JSONL sink。

## Runtime profiles

Gateway bootstrap semantics now live in `gateway/runtime_bootstrap.py`, while ROS subscription binding is centralized in `gateway/runtime_ingress.py`.

默认配置：

- `EMBODIED_ARM_RUNTIME_PROFILE=target-runtime`
- `EMBODIED_ARM_ALLOW_SIMULATION_FALLBACK=false`
- `EMBODIED_ARM_ENABLE_LOCAL_PREVIEW_COMMANDS=false`

该默认行为是 **fail-closed**：当 ROS2 bridge 不可用时，gateway 保持 `bootstrap` readiness，而不是本地伪装成可执行 runtime。

显式本地联调模式：

```bash
export EMBODIED_ARM_RUNTIME_PROFILE=dev-hmi-mock
export EMBODIED_ARM_ALLOW_SIMULATION_FALLBACK=true
export EMBODIED_ARM_ENABLE_LOCAL_PREVIEW_COMMANDS=true
python -m gateway.main
```

该模式下 gateway 仍投影 canonical `maintenance` / preview 语义，仅允许本地 HMI/维护动作联调；任务执行仍要求权威 ROS runtime。

## Generated contract sync

- `docs/generated/runtime_contract_manifest.json` and `docs/generated/runtime_contract_summary.md` are generated from code by `scripts/generate_contract_artifacts.py`.
- Gateway consumes `gateway/generated/runtime_contract.py`, and the frontend consumes `frontend/src/generated/runtimeContract.ts`; both are generated from backend authoritative readiness contracts in `arm_readiness_manager/contract_defs.py`.
- Gateway now prefers typed shadow topics for readiness / task status / diagnostics summary / calibration profile / target array, while retaining JSON compatibility topics for transitional consumers.
- Bringup / lifecycle supervision now also emits `/arm/bringup/status_typed` alongside `/arm/bringup/status`.
- `scripts/verify_repository.sh` runs `scripts/generate_contract_artifacts.py --check` to prevent drift between code and documentation.
