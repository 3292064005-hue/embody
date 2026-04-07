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
- `joint_position[5]`
- `joint_velocity[5]`
- `last_stage`
- `last_kind`
- `last_result`
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
- 周期性 `REPORT_STATE` 独立于任务控制
- 急停/限位触发会更新 fault code，并异步发 `REPORT_FAULT`

## 联调建议

上位机侧保持原项目默认：

- `stm32_port=/dev/ttyUSB0`
- `baudrate=115200`

这样可以直接对接 `upper_computer/backend/embodied_arm_ws/src/arm_hardware_bridge/arm_hardware_bridge/stm32_serial_node.py` 与 `hardware_command_dispatcher_node.py`。
