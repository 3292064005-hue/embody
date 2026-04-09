# Runtime Lanes

本文件说明当前 split-delivery 仓库对各 runtime lane 的**真实能力语义**。

## 单一事实来源

当前 lane 默认值以：

- `upper_computer/backend/embodied_arm_ws/src/arm_bringup/config/runtime_profiles.yaml`

为唯一配置事实来源；`launch_factory.py` 从该文件加载 lane manifest，并把能力参数下发给 motion planner 与 ESP32 link 节点。

## Canonical lanes（当前唯一正式 lane 名称）

### Preview lanes

- `sim_preview`：默认预览仿真 lane。camera source=`mock`，mock profile=`authoritative_demo`。
- `sim_perception_preview`：空感知预览 lane。camera source=`mock`，mock profile=`realistic_empty`。
- `real_preview`：真实视觉入口预览 lane。camera source=`topic`，要求外部向 `/arm/camera/image_raw` 提供帧输入。
- `hybrid_preview`：topic 视觉 + simulated STM32 预览 lane。
- `hw_preview`：硬件链路预览 lane；当前仍使用 `camera_source=mock`，不宣称真实视觉帧已在线。
- `full_demo_preview`：演示入口，包含 RViz。

### Authoritative simulation lanes

- `sim_authoritative`：仓内已验证的 authoritative simulation lane。planning capability=`validated_sim`，scene/grasp provider 维持 `embedded_core`，STM32 语义=`authoritative_simulation`，frame ingress 使用 synthetic preview。
- `full_demo_authoritative`：包含 RViz 与 ESP32 gateway 的 authoritative simulation demo lane。

> `*_preview` lane 仍是 preview 语义；`*_authoritative` lane 仅代表**仓内已验证的仿真 authoritative 主线**，不等价于 validated live / 真机 authoritative execution。

## Backward compatibility aliases

为兼容旧脚本与旧 launch 入口，以下历史名称仍可用，但都会被归一化到新的 preview lane：

- `official_runtime` -> `sim_preview`
- `sim` -> `sim_preview`
- `sim_perception_realistic` -> `sim_perception_preview`
- `real` -> `real_preview`
- `hybrid` -> `hybrid_preview`
- `hw` -> `hw_preview`
- `full_demo` -> `full_demo_preview`
- `authoritative_runtime` -> `sim_authoritative`
- `sim_validated` -> `sim_authoritative`
- `full_demo_validated` -> `full_demo_authoritative`

兼容别名仅用于迁移期入口，不应再作为新文档、新脚本、新发布说明中的 canonical lane 名称。

## Planning capability semantics

当前仓库已经显式区分 planning capability，而不是再把 fallback 结果伪装成“真实 MoveIt 可用”：

- `disabled`：规划能力关闭；plan request 必须 fail-closed。
- `contract_only`：仅允许契约级/演示级 planning fallback；**不是 authoritative planning**。
- `validated_sim`：已验证的仿真 authoritative planning。
- `validated_live`：已验证的真机 authoritative planning。

### 当前默认值

当前所有 canonical preview lanes 的默认值为：

- `enable_moveit: false`
- `planning_capability: contract_only`
- `planning_authoritative: false`
- `planning_backend_name: fallback_contract`

这表示：

1. 仓库默认不声称 MoveIt 真正闭环；
2. motion planner readiness 不会因为 fallback 存在就报 `planner_ready`；
3. orchestrator runtime planning request 会在 non-authoritative planning 条件下被显式拒绝，而不是假成功放行；
4. UI 若暴露任务入口，必须同步显示 preview / contract-only 门禁原因，而不是渲染成“默认可执行”。

### authoritative simulation lanes

`sim_authoritative/full_demo_authoritative` 会切换为：

- `planning_capability: validated_sim`
- `planning_authoritative: true`
- `planning_backend_name: validated_sim_runtime`
- `planning_backend_profile: validated_sim_default`
- `scene_provider_mode: embedded_core`
- `grasp_provider_mode: embedded_core`

它们的目标是提供**仓内可验证的 authoritative simulation 主线**，让 task orchestrator、planner、planner/dispatcher/feedback/HMI frame preview 进入同一条可执行闭环；scene/grasp provider 暂不宣传为独立 runtime service。

## Manual / maintenance command semantics

maintenance/manual 命令现在按**命令粒度**定义 readiness，而不是再被 `motion_planner` 整体连坐：

- `jog`
- `servoCartesian`
- `gripper`
- `recover`

这些命令的默认最小依赖是：

- `ros2`
- `task_orchestrator`
- `hardware_bridge`

因此：

- preview lane 下 task planning 仍然会被 `planner_contract_only` 拒绝；
- 但 maintenance/manual 控制不再因为 planner 非 authoritative 而被整体锁死。

## Scene / grasp provider semantics

当前 provider mode 分为两层：

- preview lanes 默认：
  - `scene_provider_mode: embedded_core`
  - `grasp_provider_mode: embedded_core`
- 所有当前正式 lanes：
  - `scene_provider_mode: embedded_core`
  - `grasp_provider_mode: embedded_core`

motion planner 现在通过 adaptor factory 选择 provider，而不是把 runtime node 与 planner 逻辑硬编码在一起。当前正式 lane 的约束是：

- preview lanes 保留嵌入式可运行性；
- authoritative simulation lanes 暂不把 scene/grasp 宣传为独立 runtime-service provider；
- `runtime_service` 适配层保留为后续 validated_live/provider boundary 收口预留，不进入当前正式主线。

## ESP32 stream semantics

ESP32 板级状态与视觉帧输入链已经拆分：

- preview lanes：
  - `esp32_stream_semantic: reserved`
  - `esp32_frame_ingress_live: false`
- authoritative simulation lanes：
  - `esp32_stream_semantic: synthetic_frame`
  - `esp32_frame_ingress_live: true`

这表示：

- preview lanes 下板级 `/stream` endpoint 仍是**预留语义**；
- authoritative simulation lanes 会由 Gateway/HMI 消费 synthetic frame preview，用于仿真执行链的操作级观测；
- `sourceEsp32Online=true` 仍不自动等价于真实摄像头 transport 在线。

## STM32 authority semantics

当前 STM32F103C8 固件仍主要承担：

- 串口协议承载
- ACK / NACK
- REPORT_STATE / REPORT_FAULT
- 状态推进与合同联调

它当前**不应被表述为已验证的真实 actuator controller**。因此：

- 在 preview lanes 中，它仍只是 transport / protocol / upper-computer 联调固件；
- 在 authoritative simulation lanes 中，它只提升为 `authoritative_simulated_transport`，用于仓内 validated_sim 闭环；
- 当前正式 validated_sim 执行 authority 仍是 dispatcher/feedback 主链；
- `real_authoritative` 已预留为 `ros2_control` live execution backbone 的唯一正式提升路径，但在 live planning backend 与 execution backbone 同时声明前，仍保持 fail-closed 预览语义；
- 不应把当前仓库的 live 执行语义宣传成已验证的真机 authoritative motion execution。

## 对上层的影响

- preview lanes 下 readiness `motion_planner` check：会报告 `planner_contract_only`，而不是 `planner_ready`。
- authoritative simulation lanes 下 task orchestrator 可以进入 validated_sim authoritative planning 主线。
- system/hardware projection：会区分 `ESP32 online`、`FRAME ingress live`、`preview_simulated_transport` 与 `authoritative_simulated_transport`。
- 前端顶部状态栏：会分别显示 ESP32 板级状态与 frame ingress 状态，不再把两者混成一个 Camera 绿灯。
- 维护页中的点动 / 伺服 / 夹爪 / recover 将按独立命令策略放行；task start 在 preview lanes 被拒绝，在 authoritative simulation lanes 进入正式仿真执行路径。
- HMI 顶栏会在 STM32 执行链不是 authoritative real transport 时显式打出 `PREVIEW_EXEC` 标记；当进入 authoritative simulation lane 时，则会显示 `STM32 AUTH-SIM`。


## HMI capability exposure

- `*_preview` lanes keep the task workbench read-only. The side navigation marks task features as preview-only and the task center only exposes history/audit views.
- `*_authoritative` lanes expose the full task workbench, template selection, and start controls.

- `real_authoritative` 在 `ros2_control` controller action server 未就绪时，`motion_executor` readiness 必须保持非 ready，`startTask` 继续 fail-closed。
