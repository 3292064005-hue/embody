# Embodied Arm — Split Delivery (Upper Computer / ESP32-S3 / STM32F103C8)

本交付把原始一体化仓库拆成三部分，同时保留原项目中的协议、状态字段、命令语义、启动默认值与文档：

- `upper_computer/`：上位机，保留原始 `frontend + gateway + backend/embodied_arm_ws + docs + scripts` 运行形态
- `esp32s3_platformio/`：ESP32-S3 PlatformIO 固件，承接原项目中的 Wi‑Fi / stream endpoint / board health / voice event 扩展语义
- `stm32f103c8_platformio/`：STM32F103C8 PlatformIO 固件，承接原项目中的串口帧协议、ACK/NACK、REPORT_STATE、REPORT_FAULT 与执行语义

## 保留的原项目关键细节

### 上位机
- 保留原始目录与启动方式：`frontend/`、`gateway/`、`backend/embodied_arm_ws/`
- 保留原始 runtime lane 约束：
  - `stm32_port=/dev/ttyUSB0`
  - `esp32_stream_endpoint=http://esp32.local/stream`
  - `real/hybrid` 相机链仍由 `/arm/camera/image_raw` 进入上位机
- 保留 `docs/`、`scripts/`、`generated runtime contract` 等原有工程资产

### ESP32-S3
- 对应原项目中的：
  - `arm_hardware_bridge/esp32_link_node.py`
  - `arm_esp32_gateway/*`
  - `launch_factory.py` 中 `esp32_stream_endpoint=http://esp32.local/stream`
- 固件提供：
  - `/healthz`
  - `/status`
  - `/stream`
  - `/voice/events`
  - `/voice/phrase`
  - `/voice/commands`
- 保留 Wi‑Fi transport、stream endpoint、board health、voice event 的原始语义

### STM32F103C8
- 对应原项目中的：
  - `docs/SERIAL_PROTOCOL.md`
  - `arm_backend_common/protocol.py`
  - `arm_backend_common/enums.py`
  - `arm_hardware_bridge/stm32_serial_node.py`
  - `arm_hardware_bridge/hardware_command_dispatcher_node.py`
  - `arm_hardware_bridge/hardware_state_aggregator_node.py`
- 固件保留的协议与命令：
  - SOF=`0xAA55`, EOF=`0x0D0A`, CRC16(Modbus)
  - `HOME / STOP / SET_JOINTS / OPEN_GRIPPER / CLOSE_GRIPPER / EXEC_STAGE / QUERY_STATE / RESET_FAULT / ACK / NACK / REPORT_STATE / REPORT_FAULT`
  - payload 继续使用 UTF-8 JSON
  - 维持 `home_ok / gripper_ok / gripper_open / motion_busy / limit_triggered / estop_pressed / hardware_fault_code / joint_position / joint_velocity / last_stage / last_kind / last_result / last_sequence / task_id`

## 推荐使用顺序

1. 先在 `upper_computer/` 跑 `runtime_sim.launch.py` 验证上位机逻辑
2. 再烧录 `stm32f103c8_platformio/`，接入 `/dev/ttyUSB0`
3. 再烧录 `esp32s3_platformio/`，确认 `http://esp32.local/stream` 与 `/healthz`
4. 最后把上位机 runtime lane 切到 `hybrid/real`

更细的映射与集成说明见 `docs/split_mapping.md`。
