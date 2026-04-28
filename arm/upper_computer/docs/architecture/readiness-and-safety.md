# Readiness and Safety

> Audience: gateway, frontend, backend, QA
> Owner: readiness / safety
> Status: canonical
> Source of Truth: `arm_readiness_manager/contract_defs.py`, generated runtime contracts, gateway policy enforcement
> Last Update Rule: readiness fields, mode rules, command policy, or safety gates change together.

> 统一术语引用：本文涉及的 command plane、runtime interface、capability descriptor、receipt / audit / log 闭环统一定义见 [`terms-and-reference-blocks.md` §3](terms-and-reference-blocks.md#3-命令与治理术语块)。runtime tier / runtimeSurfaceState 统一定义见 [`terms-and-reference-blocks.md` §2](terms-and-reference-blocks.md#2-运行时治理术语块)。

## 1. 本文负责什么 / 不负责什么

### 本文负责

- readiness 分层与公开字段语义
- controller mode / runtime phase / task stage 的关系
- command gate 顺序
- observability ingress 的治理要求

### 本文不负责

- 不定义 canonical lane / promotion marker
- 不定义 REST route 列表
- 不记录验证结果

## 2. Readiness 是分层的，不是单一布尔值

公开 readiness 至少区分：

- `runtimeHealthy`
- `modeReady`
- `commandPolicies`
- `commandSummary`
- `authoritative`
- `simulated`
- `authorityState`
- `commandSurfaceState`
- `taskExecutionState`
- `runtimeFingerprint`
- `runtimeDeliveryTrack`
- `executionBackbone`
- `runtimeSurfaceState`

其中：

- `authorityState` 表示当前 surface 是否 authoritative / simulated，以及对外公开的 authority detail
- `commandSurfaceState` 表示 command plane 是 authoritative、projected_only 还是 local_preview_only
- `taskExecutionState` 表示任务工作台是否可见、是否允许交互执行、当前 tier 与 promotion 是否生效
- `runtimeFingerprint` 用于把 build/runtime/authority 组合投影成稳定可观测指纹，便于审计与回放

兼容字段 `allReady` 仅表示 `modeReady` 的 alias，不代表“所有命令都可执行”。gateway local preview 必须保持 `runtimeHealthy=false`、`modeReady=false`、`allReady=false`，不得伪装成可启动 runtime。

## 3. Required checks

### Runtime-health required checks

- `ros2`
- `task_orchestrator`
- `motion_planner`
- `motion_executor`
- `scene_runtime_service`
- `grasp_runtime_service`
- `hardware_bridge`
- `calibration`
- `profiles`

### Mode-scoped checks

- `boot`：最小 ROS 启动检查
- `idle`：允许进入待机与任务准备
- `task`：要求 planner/executor/scene/grasp/perception/target/calibration/profile 全部满足
- `manual` / `maintenance`：允许局部控制，但仍要求硬件桥与基本 supervision 在线
- `fault` / `safe_stop`：必须保留故障处置能力

## 4. Public command policies

当前 operator-facing command policy 名称为：

- `startTask`
- `stopTask`
- `jog`
- `servoCartesian`
- `gripper`
- `home`
- `resetFault`
- `recover`

这些 policy 至少要表达：

- 是否允许
- 缺失的 checks
- mode 限制
- 失败原因

## 5. Command gate 顺序

统一 public command 执行顺序应为：

1. **role gate**
2. **policy gate**
3. **runtime interface gate**
4. **transport / execution**
5. **receipt / audit / log**

只要其中任一前置门失败，系统都必须 fail-closed，不得继续往下执行。更基础的术语定义见 [`terms-and-reference-blocks.md` §3](terms-and-reference-blocks.md#3-命令与治理术语块)。

## 6. Controller mode 与 runtime phase

### 语义字段

- `controllerMode`：控制器的当前操作模式
- `runtimePhase`：运行时阶段
- `taskStage`：任务阶段

兼容 alias：

- `mode -> runtimePhase`
- `operatorMode -> controllerMode`
- `currentStage -> taskStage`

新实现应优先使用语义字段，不再扩散 alias。

## 7. Safety policy 的边界

Safety policy 的目标不是“尽量让命令发出去”，而是：

- 在条件不满足时显式拒绝
- 给出清晰拒绝原因
- 不把 preview/fallback 写成 authoritative
- 让 blocked/failed/success 都可追踪

### 典型 fail-closed 情形

- runtime snapshot stale
- required checks 缺失
- mode 不允许
- runtime interface inactive
- promotion 不满足导致 public tier 不能提升

## 8. Observability ingress 的规则

`vision_observability` 与 `voice_observability` 也应受到 runtime interface gate 管理。它们虽然不是 execution command，但依然属于受治理的 runtime ingress：

- active 时允许进入 projection/receipt/log
- inactive 时必须 fail-closed 并留下 blocked 记录
- 不得因为“只是观测”就绕过治理链

## 9. Frontend / Gateway 的消费原则

### Gateway

负责把底层 readiness、policy、surface 汇总成对外稳定形状，并统一输出 `authorityState`、`commandSurfaceState`、`taskExecutionState`、`runtimeFingerprint` 四个公开真值层。gateway 不得再把 local preview 写成“ready but blocked later”的伪闭环语义。

### Frontend

优先消费：

- `authorityState`
- `commandSurfaceState`
- `taskExecutionState`
- `runtimeFingerprint`
- `runtimeSurfaceState`
- `commandPolicies`
- `commandPlanes`
- `capabilityDescriptors`

前端不应重新推断更高层 truth；它只能展示和约束，不应重新定义 authoritative 状态。兼容字段仅用于旧页面过渡，不得覆盖新分层语义。

## 10. 修改检查表

修改以下内容时，至少同步检查：

| 变更内容 | 至少同步检查 |
|---|---|
| readiness 字段 | generated contract、`interfaces/api-contract.md`、frontend store |
| command gate 顺序 | gateway tests、相关 router、receipt/audit tests |
| observability ingress gate | runtime projection、receipts、frontend observability UI |
| alias 字段 | compatibility 文档、前端兼容消费层 |
