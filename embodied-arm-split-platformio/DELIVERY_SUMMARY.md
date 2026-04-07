# Delivery Summary

## 已做的拆分

- 上位机：完整保留到 `upper_computer/`
- ESP32-S3：拆为 `esp32s3_platformio/`
- STM32F103C8：拆为 `stm32f103c8_platformio/`

## 明确保留的原项目细节

- `upper_computer` 中的 `frontend/gateway/backend/docs/scripts`
- launch 默认值：
  - `stm32_port=/dev/ttyUSB0`
  - `esp32_stream_endpoint=http://esp32.local/stream`
- voice event topic 语义：`/arm/voice/events`
- STM32 帧协议：SOF/EOF/CRC16/JSON payload/ACK/NACK/REPORT_STATE/REPORT_FAULT
- 硬件状态字段：`home_ok/gripper_ok/gripper_open/motion_busy/limit_triggered/estop_pressed/hardware_fault_code/joint_position/joint_velocity/last_stage/last_kind/last_result/last_sequence/task_id`

## 我没有伪称完成的部分

### 1. ESP32 真摄像头流
我保留了 `http://esp32.local/stream` endpoint 和相关 metadata，但没有在 generic S3 板上强绑定某个 camera 模组引脚或图库。这样做是为了不虚构你未确认的板级硬件。

### 2. STM32 真机电机/编码器驱动
我实现的是对齐上位机协议和语义的 firmware 骨架，包含 ACK/NACK/状态机/急停限位输入/周期上报；但没有伪造某个具体舵机驱动芯片、编码器型号或机械臂关节电控板的专有驱动。

### 3. 上位机运行方式
我没有把上位机硬改成 PlatformIO 目录，因为那会破坏 ROS2 + FastAPI + Vue 的真实运行方式。为了保留原项目细节，上位机部分保持原生结构，只在顶层拆成独立部分。
