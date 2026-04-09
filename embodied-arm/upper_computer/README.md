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
- `arm_esp32_gateway`
- `arm_readiness_manager`
- `arm_safety_supervisor`
- `arm_camera_driver`
- `arm_perception`
- `arm_scene_manager`
- `arm_grasp_planner`
- `arm_motion_planner`
- `arm_motion_executor`
- `arm_task_orchestrator`
- `arm_bt_runtime`
- `arm_bt_nodes`
- `arm_diagnostics`
- `arm_logger`

## Runtime supervision / Compatibility / Experimental

- Runtime supervision：`arm_lifecycle_manager`
- Compatibility：`arm_task_manager / arm_motion_bridge / arm_vision`
- Experimental：`arm_hmi`
- Active runtime support（测试/合同支撑包）：`arm_common / arm_interfaces / arm_mock_tools / arm_sim / arm_tools / arm_tests`

正式运行链承诺 Runtime Core；`arm_esp32_gateway` 已进入正式 Runtime Core，`arm_hmi` 仍保持 experimental。active gate 允许最小化 support 包参与测试与合同校验，但 compatibility/experimental 包不进入正式 active runtime lane。

## Runtime semantic fields

对外契约已拆分为三组字段：

- `controllerMode`：稳定控制模式（`idle/manual/task/maintenance`）
- `runtimePhase`：执行相位（`boot/idle/perception/plan/execute/verify/safe_stop/fault`）
- `taskStage`：UI 任务阶段（`created/perception/plan/execute/verify/done/failed`）

此外，运行时公共契约已进入“双轨迁移”阶段：`arm_interfaces` 是唯一权威接口源，`arm_msgs` 仅保留为 compatibility mirror；验证链会通过 `scripts/sync_interface_mirror.py --check` 阻止两者漂移。并行为 readiness / task status / diagnostics summary / calibration profile / target array 提供 typed shadow topics，同时保留旧 JSON compatibility topics。

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

运行时能力矩阵的唯一真源为 `backend/embodied_arm_ws/src/arm_bringup/config/runtime_authority.yaml`。修改后先执行：

```bash
python scripts/sync_runtime_authority.py --check
python scripts/generate_contract_artifacts.py --check
```

随后再跑常规验证入口：

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
# 或显式使用新的 canonical lane 名称：
# ros2 launch arm_bringup runtime.launch.py runtime_lane:=sim_preview
# ros2 launch arm_bringup runtime_real_candidate.launch.py
# ros2 launch arm_bringup runtime_real_validated_live.launch.py
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

- `sim_preview/full_demo_preview`：camera runtime 使用内置 preview mock 源（`authoritative_demo`），Gateway `/api/vision/frame` 默认返回目标态势摘要或 synthetic preview，而不是 authoritative video transport。
- `sim_authoritative/full_demo_authoritative`：camera runtime 仍使用 mock 源，但会通过 synthetic frame preview 把 `frame_ingress_live=true` 投影到 HMI，用于仓内已验证的 authoritative simulation 操作链。
- `sim_perception_preview`：camera runtime 使用 `realistic_empty` mock 源，若无外部目标则 task orchestrator 进入 `BLOCKED_BY_PERCEPTION`。
- `real_preview/hybrid_preview`：camera runtime 使用 `topic` 源，要求外部视觉/采集侧向 `/arm/camera/image_raw（标准 sensor_msgs/Image）` 提供帧输入，再由 perception runtime 生成权威 `/arm/vision/target`。历史 JSON 帧入口保留在 `/arm/camera/image_raw_compat`，仅作为迁移兼容通道。兼容 JSON 入口默认不会再反向回灌标准 `/arm/camera/image_raw`，避免 camera runtime 自订阅造成重复 frame summary；只有显式打开 `republish_compat_frames_as_standard_image=true` 才允许兼容帧回灌。
- 兼容别名 `sim/full_demo/sim_perception_realistic/real/hybrid` 仍可用，但新文档、新脚本必须优先使用 `*_preview` canonical lanes；authoritative simulation 兼容别名包括 `authoritative_runtime -> sim_authoritative`。
- ESP32 `/stream` 在 preview lanes 仍以板级 endpoint / health 语义为主；authoritative simulation lanes 会把 `stream_semantic=synthetic_frame`、`frame_ingress_live=true` 显式投影到 HMI，但这仍不等价于真实摄像头 transport。

## Planning capability truthfulness

当前仓库已经显式区分 planning capability，避免把 fallback/demo 路径伪装成 authoritative MoveIt：

- `disabled`：规划能力关闭，request fail-closed
- `contract_only`：仅契约级/演示级 fallback，**不是 authoritative planning**
- `validated_sim`：已验证仿真规划
- `validated_live`：仅当 `validated_live_backbone_declared`、`target_runtime_gate_passed`、`hil_gate_passed`、`release_checklist_signed` 四项证据全部满足时，才允许对外宣称的真机 authoritative 能力。其中 backbone 由 live planning backend + ros2_control execution backbone + live vision ingress + hardware command path 联合声明，target-runtime gate 来自 `artifacts/release_gates/target_runtime_gate.json`。

当前 canonical preview runtime lanes 的默认值为：

- `enable_moveit=false`
- `planning_capability=contract_only`
- `planning_authoritative=false`
- `planning_backend_name=fallback_contract`

新增的 authoritative simulation lanes（当前仍以 embedded provider + dispatcher authority 为正式主线）：

- `sim_authoritative`
- `full_demo_authoritative`

会切换为：

- `planning_capability=validated_sim`
- `planning_authoritative=true`
- `planning_backend_name=validated_sim_runtime`
- `planning_backend_profile=validated_sim_default`
- `scene_provider_mode=runtime_service`（authoritative lanes）
- `grasp_provider_mode=runtime_service`（authoritative lanes）
- `planning_backend_profiles.yaml` 中 `validated_sim_default.declared=true`，由 `motion_planner_node` / `launch_factory` 同步消费

因此：

- preview lanes 下 motion planner readiness 默认会给出 `planner_contract_only`，而不是 `planner_ready`；
- authoritative simulation lanes 下 orchestrator 可以走已验证仿真 planning 主线；
- maintenance/manual 控制命令现在按独立 command policy 放行，不再因为 planner 非 authoritative 被整体连坐；
- 预览/离线契约路径仍会带上 `planningAuthoritative=false` 元数据，而 authoritative simulation 会显式带上 `planningCapability=validated_sim`。

## Maintenance / recovery command semantics

- `jog / servoCartesian / gripper / recover` 现在按命令粒度评估 readiness。
- `manual/maintenance` 默认最小依赖为 `ros2 + task_orchestrator + hardware_bridge`。
- `startTask` 仍需要 authoritative planning 能力；preview lanes 会以 `planner_contract_only` 明示拒绝，而 `sim_authoritative/full_demo_authoritative` 会开放已验证仿真执行路径。
- `home / resetFault / recover` 现在同时在 gateway 与 ROS 入口按 authoritative `commandPolicies` fail-closed；stale authoritative readiness snapshot 会直接拒绝命令与任务启动，并把 gateway 投影的 `runtimeTier` 降回 `preview`。
- `/api/system/recover` 已进入前端维护主链，作为显式运行时恢复命令，而不是隐藏后门接口。

## 标定与运行时可写状态

- 活动标定默认写入 `${XDG_STATE_HOME:-~/.local/state}/embodied-arm/gateway_data/active_calibration.yaml`
- backend 源码中的 `default_calibration.yaml` 仅作为只读兼容回退源
- Gateway observability 默认写入 `${XDG_STATE_HOME:-~/.local/state}/embodied-arm/gateway_observability/*.jsonl`
- 通过 `EMBODIED_ARM_GATEWAY_DATA_DIR` / `EMBODIED_ARM_OBSERVABILITY_DIR` 可继续显式覆盖路径

```bash
make target-env-bootstrap
```

## Runtime safety authority

- `src/arm_bringup/config/safety_limits.yaml` 现在是运行时 safety authority，而不再只是 compatibility mirror。
- `motion_executor` 会在生成/归一化执行目标时校验关节位置、夹爪力与 execution target；越界命令会 fail-closed 并发布终止反馈。
- `hardware_command_dispatcher` 会在串口下发前校验 `SERVO_CARTESIAN` / `JOG_JOINT` / gripper force 等手动命令，防止上位机把超限命令直接落到板端。
- Gateway 的 jog/servo 输入限制也从同一份 safety authority 读取，避免前后端各自写死不同阈值。
- Gateway 运行时配置加载器现在按文件签名自动刷新；`/api/system/readiness` 会同时投影 `manualCommandLimits` 与 `runtimeConfigVersion`，前端维护页优先消费运行时回传限制，生成契约只作为冷启动回退。

## Validation and release gates

- `make verify` 通过 `scripts/verify_repository.sh` 顺序执行 backend-full / backend-active / active-profile-consistency / interface-mirror-drift / contract-artifacts / runtime-contracts / gateway / frontend-deps / frontend-typecheck-app / frontend-typecheck-test / frontend-unit / frontend-build / frontend-e2e / audit，并把日志落到 `artifacts/repository_validation/`。
- `make test-backend` 与 `make test-backend-active` 现在同时可用：前者覆盖完整后端仓库导入与测试收集，后者保留正式 active runtime lane。
- `npm run test:e2e` 会先自动执行 `npm run build`；若当前环境策略禁止系统 Chromium，脚本会明确输出 skipped，而不是伪装成通过的浏览器验证。
- `make ros-target-validate` 即使失败也会生成 `artifacts/release_gates/target_runtime_gate.json`，并把失败步骤标记为 `failed`/`blocked`。

`official_runtime.launch.py` remains a compatibility alias to the `sim_preview` lane. Additional compatibility aliases include `authoritative_runtime -> sim_authoritative`, `sim_validated -> sim_authoritative`, and `full_demo_validated -> full_demo_authoritative`.


- HMI capability exposure follows runtime authority: preview lanes keep task workbench read-only, authoritative lanes expose the full task workbench.

Authoritative lanes now promote `scene/grasp` onto the shared `runtime_service` boundary and launch the corresponding provider nodes inside the runtime graph. The `real_candidate` candidate lane and `real_validated_live` validated lane both remain fail-closed until the canonical validated-live backbone is declared, the target-runtime gate report reaches `passed`, and `backend/embodied_arm_ws/src/arm_bringup/config/validated_live_evidence.yaml` marks both HIL and release-checklist artifacts as `passed`.

In addition, `startTask` must remain blocked whenever the `motion_executor` readiness check reports that either ros2_control controller action server is unavailable; live declaration alone is not treated as execution readiness.


Generated runtime/profile artifacts are now fail-fast requirements for repository and target-runtime validation. Missing or malformed runtime profiles or planning backend profiles no longer silently fall back to baked-in live defaults.
