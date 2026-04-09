# STM32 Serial Protocol (Authoritative Split Delivery Contract)

本协议文档以当前代码实现为准，对齐以下权威实现：

- `backend/embodied_arm_ws/src/arm_backend_common/arm_backend_common/enums.py`
- `backend/embodied_arm_ws/src/arm_backend_common/arm_backend_common/protocol.py`
- `../stm32f103c8_platformio/include/protocol.hpp`
- `../stm32f103c8_platformio/src/protocol.cpp`
- `../stm32f103c8_platformio/src/main.cpp`

## 帧格式

- SOF: `0xAA55`
- Command: `uint8`
- Sequence: `uint8`
- Payload length: `uint16`
- Payload: UTF-8 JSON bytes
- CRC16: Modbus
- EOF: `0x0D0A`

Python 与 STM32 两端都按相同帧格式进行 encode/decode。CRC 校验失败、SOF/EOF 异常、长度不匹配都必须丢帧，不得当作有效控制报文处理。

## 当前正式支持的命令集合

### 上位机 -> STM32

- `HEARTBEAT`
- `HOME`
- `STOP`
- `SET_JOINTS`
- `OPEN_GRIPPER`
- `CLOSE_GRIPPER`
- `EXEC_STAGE`
- `QUERY_STATE`
- `RESET_FAULT`

### STM32 -> 上位机

- `ACK`
- `NACK`
- `REPORT_STATE`
- `REPORT_FAULT`

> 说明：旧文档中出现过 `ESTOP / SAFE_HALT / JOG / GRIPPER` 等命令名，但这些**不是当前 split 固件的正式实现命令集合**，不得再作为对齐依据。

## Payload 语义

payload 继续使用 UTF-8 JSON。字段允许最小化，但以下语义由当前实现真实消费：

### `SET_JOINTS`

```json
{
  "kind": "SET_JOINTS",
  "task_id": "task-123",
  "positions": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
  "timeout_sec": 1.5
}
```

### `EXEC_STAGE`

```json
{
  "kind": "EXEC_STAGE",
  "task_id": "task-123",
  "stage": "grasp",
  "target_id": "target_red_001"
}
```

### `REPORT_STATE`

固件按当前实现回传以下状态语义子集（字段可扩展，但不能删改既有含义）：

- `home_ok`
- `gripper_ok`
- `gripper_open`
- `motion_busy`
- `limit_triggered`
- `estop_pressed`
- `hardware_fault_code`
- `joint_position`
- `joint_velocity`
- `last_stage`
- `last_kind`
- `last_result`
- `transport_state`
- `transport_result`
- `actuation_state`
- `actuation_result`
- `last_sequence`
- `task_id`
- `result_code`
- `execution_state`

### `REPORT_FAULT`

```json
{
  "fault": "limit_triggered",
  "code": 4,
  "message": "joint limit triggered",
  "result_code": "limit_triggered",
  "execution_state": "fault"
}
```

## 执行反馈规范

当前 split 固件已把反馈语义固定为：

- `ACK`: `transport_state=accepted`, `transport_result=accepted`，兼容别名 `result_code=accepted`；actuation 仍为 pending
- `NACK`: `transport_state=rejected`, `transport_result=rejected`，兼容别名 `execution_state=failed`
- `REPORT_STATE`: `transport_state=completed`，`actuation_state=succeeded|canceled|fault`，兼容别名 `result_code/execution_state` 同步投影
- `REPORT_FAULT`: `transport_state=completed`，`actuation_state=fault`

上位机 dispatcher / executor 必须优先依据 `command_id + transport_state/transport_result + actuation_state/actuation_result` 相关联，而不是只看串口成功发送。

## 去重与超时行为

STM32 固件当前实现包含 sequence 去重窗口。重复 sequence 的控制帧不得重复执行危险动作；上位机应以 ACK/NACK/REPORT_STATE 为最终语义反馈，而不是只看串口发送成功。

## 安全语义

- `STOP` 是当前正式的急停/停机控制命令入口。
- `RESET_FAULT` 只负责清除可恢复故障状态，不代表自动恢复任务。
- 串口协议版本变化必须同步更新根级 release manifest 中的 `protocolVersion`。

## 版本治理要求

当前交付基线要求：

- 文档、Python 端协议、STM32 固件协议三者保持一致
- 新增命令必须同时补齐：`enums.py`、`protocol.py`、固件解析逻辑、本文档
- 不允许只改文档或只改固件后再靠口头约定联调
