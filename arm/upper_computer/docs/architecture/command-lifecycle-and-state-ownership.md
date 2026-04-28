# Command Lifecycle and State Ownership

> Audience: implementers / reviewers / gateway / frontend / backend
> Owner: architecture / command governance
> Status: canonical
> Source of Truth: gateway command pipeline, runtime projection, task orchestrator runtime, ROS bridge
> Last Update Rule: when command status semantics, producer ownership, or lifecycle projections change, update this document in the same change.

## 1. 目的

本文补齐实现者视角的三类事实：

- 命令 API 首次返回到底表示什么
- 哪些状态字段由哪一层拥有
- 从前端到硬件回执的主链由谁负责哪一段

## 2. 命令生命周期语义

当前系统将命令生命周期拆成两层：

1. **受理层（accepted）**：Gateway 已完成角色校验、readiness gate、runtime interface gate，并且底层 transport 已接受命令。
2. **完成层（success / failed / blocked / rejected / observed）**：必须以后端 authoritative state、command receipt、task progress、hardware state 为准，不允许由首次 REST 返回伪造。

因此：

- `/api/system/*`、`/api/hardware/*`、`/api/task/stop` 首次返回只表达 **accepted**。
- `task.start` 也只表达任务请求已受理，真正执行结果看 task progress / history。
- local preview 分支会明确标识 `localPreviewOnly=true`，避免被误读成 authoritative completion。

## 3. 状态所有权矩阵

| 状态/字段 | 权威生产者 | 主要消费者 | 说明 |
|---|---|---|---|
| `audit.status` | Gateway command pipeline | Frontend audit view / reviewers | 记录 accepted / success / failed / blocked / rejected / observed 等生命周期事件 |
| `command receipt.status` | Gateway command pipeline / observability ingress | Logs/Maintenance 页面、联调诊断 | 用于追踪命令是否 accepted / success / failed / blocked / rejected / observed |
| `system.runtimePhase` | Backend runtime / gateway projection | Frontend dashboard / maintenance | 不能由设置页或本地偏好页改写 |
| `system.controllerMode` | Backend runtime + gateway guarded mutation | Frontend maintenance / dashboard | 前端只能请求切换，不能自定义 authoritative mode |
| `hardware.*` 执行状态 | Hardware bridge / hardware interface / gateway projection | Frontend robot panels / safety guards | 手动命令完成态必须看这里 |
| `task.current` / `task.history` | Task orchestrator / gateway projection | TaskCenter / dashboard | 任务执行结果不以 start/stop 首次返回为准 |
| `settings store` | Frontend localStorage | 当前 HMI 页面与交互细节 | 仅本地偏好，不属于系统 authority |

## 4. 主链路责任分段

| 链路段 | 负责模块 | 关键文件 |
|---|---|---|
| UI 发起命令 | Frontend store / command bus | `frontend/src/stores/*.ts`, `frontend/src/services/commands/commandBus.ts` |
| 角色 / readiness / runtime interface gate | Gateway command service | `gateway/command_service.py` |
| runtime transport dispatch | Gateway ROS bridge | `gateway/ros_bridge.py` |
| task orchestration | ROS2 task orchestrator | `backend/.../arm_task_orchestrator/runtime.py` |
| planning / execution | motion planner / executor | `backend/.../arm_motion_planner/*`, `backend/.../arm_motion_executor/*` |
| hardware dispatch / ACK-NACK | hardware bridge / interface / MCU | `backend/.../arm_hardware_bridge/*`, `arm_hardware_interface/*`, firmware |
| operator-facing projection | Gateway state/runtime projection | `gateway/state.py`, `gateway/runtime_projection.py` |

## 5. 变更规则

- 新命令若只完成 dispatch，不得把首次返回写成 success/completed。
- 任何命令状态语义变更，都必须同步：Gateway、frontend store、OpenAPI、日志/回执页面、测试。
- 新增“系统设置”类页面时，必须先说明其是 **local preference** 还是 **authoritative config contract**。
