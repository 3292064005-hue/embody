# STM32F103C8 PlatformIO Firmware

该固件承接原项目中的 STM32 串口执行链，而不是另起炉灶。

## 对应原仓库模块

- `upper_computer/docs/SERIAL_PROTOCOL.md`
- `upper_computer/backend/embodied_arm_ws/src/arm_backend_common/arm_backend_common/protocol.py`
- `upper_computer/backend/embodied_arm_ws/src/arm_backend_common/arm_backend_common/enums.py`
- `upper_computer/backend/embodied_arm_ws/src/arm_hardware_bridge/arm_hardware_bridge/stm32_serial_node.py`
- `upper_computer/backend/embodied_arm_ws/src/arm_hardware_bridge/arm_hardware_bridge/hardware_command_dispatcher_node.py`
- `upper_computer/backend/embodied_arm_ws/src/arm_hardware_bridge/arm_hardware_bridge/hardware_state_aggregator_node.py`

## 保留的关键协议细节

- SOF = `0xAA 0x55`
- EOF = `0x0D 0x0A`
- body = `version + command + sequence + payload_len_le + payload_json_utf8`
- checksum = CRC16(Modbus)
- payload = UTF-8 JSON

## 保留的命令集合

- `HOME`
- `STOP`
- `SET_JOINTS`（承接 `JOG_JOINT` / `SERVO_CARTESIAN`）
- `OPEN_GRIPPER`
- `CLOSE_GRIPPER`
- `EXEC_STAGE`
- `QUERY_STATE`
- `RESET_FAULT`
- `ACK`
- `NACK`
- `REPORT_STATE`
- `REPORT_FAULT`

## 保留的状态字段

- `home_ok`
- `gripper_ok`
- `gripper_open`
- `motion_busy`
- `limit_triggered`
- `estop_pressed`
- `hardware_fault_code`
- `joint_position[6]`
- `joint_velocity[6]`
- `last_stage`
- `last_kind`
- `last_result`
- `transport_state` / `transport_result`
- `actuation_state` / `actuation_result`
- `execution_state` / `result_code`（兼容别名）
- `last_sequence`
- `task_id`

## I/O 约定

- 串口：`Serial1 @ 115200`
- 板载指示灯：`PC13`
- 急停输入：`PB12`（低电平触发）
- 限位输入：`PB13`（低电平触发）

## 设计说明

- malformed frame 直接丢弃，不产生副作用
- 去重窗口内的重复命令按幂等处理：重新 ACK 并补发状态
- ACK/NACK 仅表达 transport 受理结果；动作完成、取消、故障通过 `REPORT_STATE/REPORT_FAULT` 的 actuation 字段表达
- 当前固件按 `protocol_simulator` 语义工作：除 `fault/canceled` 外，终态统一以 `protocol_*_simulated` 上浮，避免被上位机误判为真实执行成功
- 周期性 `REPORT_STATE` 独立于任务控制
- 急停/限位触发会更新 fault code，并异步发 `REPORT_FAULT`

## 联调建议

上位机侧保持原项目默认：

- `stm32_port=/dev/ttyUSB0`
- `baudrate=115200`

这样可以直接对接 `upper_computer/backend/embodied_arm_ws/src/arm_hardware_bridge/arm_hardware_bridge/stm32_serial_node.py` 与 `hardware_command_dispatcher_node.py`。
