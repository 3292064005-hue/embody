# API Contract

> Audience: frontend, gateway, QA
> Owner: gateway / public contract
> Status: canonical
> Source of Truth: `gateway/openapi/runtime_api.yaml`, generated runtime contracts, websocket event schema implemented in gateway
> Last Update Rule: REST or WebSocket payload changes must update this file and OpenAPI/generated contract in the same change.

> 统一术语引用：本文涉及的 command plane、runtimeSurfaceState、receipt 闭环统一定义见 [`../architecture/terms-and-reference-blocks.md` §2-§3](../architecture/terms-and-reference-blocks.md#2-运行时治理术语块)。

## 1. 本文负责什么 / 不负责什么

### 本文负责

- REST 与 WebSocket 的公共合同
- 共享 envelope、error shape、versioning 规则
- route family 到治理平面的对应关系

### 本文不负责

- 不定义 ROS2 topic/service/action
- 不定义 STM32 串口帧
- 不定义 runtime lane / promotion 规则

## 2. 范围

本文件统一描述：

- REST contract
- WebSocket contract
- 公共 envelope、error shape、versioning 规则

ROS2 topic/service/action 与 STM32 串口协议不在本文件定义，分别见：

- [ros2-interface-index.md](ros2-interface-index.md)
- [stm32-serial-protocol.md](stm32-serial-protocol.md)

## 3. 通用约定

### Envelope

公共 REST 返回统一走 `wrap_response(...)` 风格；调用方应把 envelope 视为 contract 的一部分，而不是把内部数据结构裸露出去。

### Error shape

错误返回至少要表达：

- HTTP status
- error code
- failure class
- human-readable message
- request / correlation context（若可用）

### Versioning

- 破坏性变更必须同步更新 OpenAPI、generated contract、frontend generated client
- 向后兼容新增字段时，应保持旧字段继续可读，直到兼容窗口结束

### Command receipts

command / observability 事件的公共回执需要稳定表达：

- command plane
- receipt class
- status（accepted / blocked / failed / success / observed / rejected）
- execution bound
- request / correlation / episode context（若存在）

统一术语定义不在本节重复展开，见 [`terms-and-reference-blocks.md` §3](../architecture/terms-and-reference-blocks.md#3-命令与治理术语块)。

## 4. REST Contract

### 4.1 Route family 与治理平面的对应关系

| Route family | 主要治理平面 | 说明 |
|---|---|---|
| `/api/system/*` | `system_control` | 系统状态变化与恢复处置 |
| `/api/task/*` | `task_control` | 任务目录、开始、停止、当前任务 |
| `/api/hardware/*` | `manual_control` 或 `system_control` | 手工操作与 mode 切换 |
| `/api/logs/*` | 读取面 | 读取 receipt / audit / diagnostics，不产生新治理平面 |
| `/api/vision/*` | observability / diagnostics | 观测与目标/画面投影 |

### 4.2 Health

- `/health/live`
- `/health/ready`
- `/health/deps`

健康检查负责表达进程与 readiness 投影，不等同于“所有命令都可以执行”。

### 4.3 System

- `/api/system/summary`
- `/api/system/readiness`
- `/api/system/home`
- `/api/system/reset-fault`
- `/api/system/recover`
- `/api/system/emergency-stop`

系统相关接口应优先映射到 `system_control` plane 或其 runtime projection，不应绕过统一命令管线。

### 4.4 Task

- `/api/task/templates`
- `/api/task/history`
- `/api/task/current`
- `/api/task/start`
- `/api/task/stop`

`/api/task/templates` 是公开任务模板目录；`/api/task/history` 是已完成任务的 ledger 读取面；`/api/task/start` 是主链关键入口。它们都必须与 router / OpenAPI 保持同名同步，不能再保留旧的 `catalog` 别名文档事实。

### 4.5 Hardware

- `/api/hardware/state`
- `/api/hardware/set-mode`
- `/api/hardware/gripper`
- `/api/hardware/jog-joint`
- `/api/hardware/servo-cartesian`

这些接口虽然面向手工操作，但仍必须经过：

- role gate
- command policy
- runtime interface gate
- receipt / audit / log

其中 `/api/hardware/servo-cartesian` 已按 gateway validation → dispatcher mapping → transport feedback closure 接入，不允许再在文档里把它描述为“未闭环占位接口”。

### 4.6 Vision / Diagnostics / Logs / Calibration

- `/api/vision/*`
- `/api/diagnostics/*`
- `/api/logs/*`
- `/api/calibration/*`

其中 `logs/receipts` 是统一回执的读取面；观测类接口可以只读，但不能私自定义另一套事件语义。

## 5. WebSocket Contract

### Bootstrap snapshot

客户端初连后应接收到 canonical bootstrap snapshot，包括：

- system
- readiness
- targets
- vision frame

最小 bootstrap envelope markers：

```json
{
  "schemaVersion": "1.1",
  "snapshotVersion": 1,
  "deliveryMode": "snapshot",
  "topicRevision": 7
}
```

Runtime bootstrap 必须在 `bootstrapComplete=true` 后，才允许把增量 topic streaming 视为 authoritative。
- task
- hardware
- diagnostics
- calibration

### 主要事件

- `system.state.updated`
- `readiness.state.updated`
- `task.progress.updated`
- `hardware.state.updated`
- `vision.targets.updated`
- `vision.frame.updated`
- `diagnostics.summary.updated`
- `calibration.profile.updated`
- `command.receipt.created`
- `audit.event.created`

### 事件一致性要求

- WebSocket 事件名称与 REST 字段语义必须一致
- 事件可以增量，但不应变成另一个事实源
- 与 OpenAPI/REST 相同的核心对象，应共享一致字段命名

## 6. 前端消费原则

- Frontend 优先消费 generated API client 与 canonical contract
- Frontend 只保留 `frontend/README.md` 到 canonical contract 的跳转，不再维护本地 API 事实页
- runtime/public surface 相关 UI 优先消费 `runtimeSurfaceState`

## 7. 修改流程

修改任一 public route 或 payload 时，至少同步完成：

1. 更新实现
2. 更新 OpenAPI
3. 更新本文件
4. 更新 frontend generated client / 消费方
5. 更新 contract 或 gateway tests
