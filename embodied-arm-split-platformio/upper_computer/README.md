# Embodied Arm Full-Stack Integrated

统一工程目录，包含前端 HMI、Gateway、ROS2 后端工作区、运行时数据与基础脚本。

## 当前正式架构

- `frontend/`：Vue3 + Pinia + Element Plus HMI
- `gateway/`：FastAPI BFF + WebSocket + 审计 + 安全门禁 + readiness 聚合
- `backend/embodied_arm_ws/`：ROS2 split-stack 工作区
- `docs/`：冻结架构、退役矩阵、测试策略、发布检查清单、安全策略
- `scripts/`：基础启动脚本与打包脚本

> 说明：`gateway_data/` 仍保留为兼容路径，但新的默认运行时可写状态根目录已迁移到 `${XDG_STATE_HOME:-~/.local/state}/embodied-arm/`。可通过 `EMBODIED_ARM_STATE_ROOT` 覆盖。

## split-stack 正式 Runtime Core

- `arm_profiles`
- `arm_calibration`
- `arm_hardware_bridge`
- `arm_readiness_manager`
- `arm_safety_supervisor`
- `arm_camera_driver`
- `arm_perception`
- `arm_scene_manager`
- `arm_grasp_planner`
- `arm_motion_planner`
- `arm_motion_executor`
- `arm_task_orchestrator`
- `arm_diagnostics`
- `arm_logger`

## Runtime supervision / Compatibility / Experimental

- Runtime supervision：`arm_lifecycle_manager`
- Compatibility：`arm_task_manager / arm_motion_bridge`
- Experimental：`arm_hmi / arm_esp32_gateway`

正式运行链只承诺 Runtime Core；experimental 包不代表正式交付能力。

## Runtime semantic fields

对外契约已拆分为三组字段：

- `controllerMode`：稳定控制模式（`idle/manual/task/maintenance`）
- `runtimePhase`：执行相位（`boot/idle/perception/plan/execute/verify/safe_stop/fault`）
- `taskStage`：UI 任务阶段（`created/perception/plan/execute/verify/done/failed`）

此外，运行时公共契约已进入“双轨迁移”阶段：权威接口源为 `arm_interfaces`，并行为 readiness / task status / diagnostics summary / calibration profile / target array 提供 typed shadow topics，同时保留旧 JSON compatibility topics。

readiness 契约已经分层：

- `runtimeHealthy`
- `modeReady`
- `commandPolicies`
- `commandSummary`
- `authoritative`
- `simulated`

兼容期内保留别名：

- `mode` -> `runtimePhase`
- `operatorMode` -> `controllerMode`
- `currentStage` -> `taskStage`
- `allReady` -> `modeReady`

前端本地权限选择器已统一命名为 `operatorRole`（`viewer/operator/maintainer`），仅通过 `X-Operator-Role` 请求头参与命令鉴权，不再与运行时 `controllerMode` 混名。

## Hardware authority semantics

当前正式链路显式区分：

- 在线
- simulated
- simulated fallback
- authoritative real hardware

默认 target-runtime 路径是 **fail-closed**：真机链路失败时，系统保持阻断，而不是自动伪装为 simulated ready。

## Validated environment lanes

### Repository validation lane

- OS: **Linux**
- Python: **3.10+**
- Node.js: **22.x**
- npm: **10.9.2**
- ROS 2: **optional** for repository unit / contract / packaging gates

### Target runtime lane

- OS: **Ubuntu 22.04 LTS**
- ROS 2: **Humble**
- Python: **3.10.x**
- Node.js: **22.x**
- npm: **10.9.2**
- STM32 real transport dependency: **pyserial>=3.5**

## 常用验证入口

```bash
make test-backend
make test-backend-active
make test-gateway
make test-frontend
make frontend-build
make test-frontend-e2e
make clean-runtime-state
make release-gate-report
make hil-template
```

## 目标环境验证入口

```bash
make target-env-check
make ros-target-validate
make ros-target-validate-docker
```

## 启动顺序

### 1) 构建 ROS2 后端

```bash
cd backend/embodied_arm_ws
colcon build --symlink-install
source install/setup.bash
ros2 launch arm_bringup runtime_sim.launch.py
```

### 2) 启动网关

```bash
pip install -r gateway/requirements.txt -c gateway/constraints.txt
python -m gateway.main
```

### 3) 启动前端

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```


## Camera runtime ingress contract

- `sim/full_demo`：camera runtime 使用内置 mock 源。
- `real/hybrid`：camera runtime 使用 `topic` 源，要求外部视觉/采集侧向 `/arm/camera/image_raw` 提供帧输入，再由 perception runtime 生成权威 `/arm/vision/target`。

## 标定与运行时可写状态

- 活动标定默认写入 `${XDG_STATE_HOME:-~/.local/state}/embodied-arm/gateway_data/active_calibration.yaml`
- backend 源码中的 `default_calibration.yaml` 仅作为只读兼容回退源
- Gateway observability 默认写入 `${XDG_STATE_HOME:-~/.local/state}/embodied-arm/gateway_observability/*.jsonl`
- 通过 `EMBODIED_ARM_GATEWAY_DATA_DIR` / `EMBODIED_ARM_OBSERVABILITY_DIR` 可继续显式覆盖路径

```bash
make target-env-bootstrap
```

## Validation and release gates

- `make verify` 通过 `scripts/verify_repository.sh` 顺序执行 backend-active / contract-artifacts / gateway / frontend / build / audit，并把日志落到 `artifacts/repository_validation/`。
- `make test-backend` 与 `make test-backend-active` 现在同时可用：前者覆盖完整后端仓库导入与测试收集，后者保留正式 active runtime lane。
- `npm run test:e2e` 会先自动执行 `npm run build`；若当前环境策略禁止系统 Chromium，脚本会明确输出 skipped，而不是伪装成通过的浏览器验证。
- `make ros-target-validate` 即使失败也会生成 `artifacts/release_gates/target_runtime_gate.json`，并把失败步骤标记为 `failed`/`blocked`。

`official_runtime.launch.py` remains a compatibility alias to the sim lane.
