# Firmware Split Integration

本文件说明 `upper_computer/` 如何对接外部 PlatformIO firmware。

## STM32F103C8

上位机默认值已经与拆分后的 STM32 firmware 对齐：

- launch 默认串口：`/dev/ttyUSB0`
- 波特率：`115200`
- command dispatcher -> `HARDWARE_STM32_TX`
- serial node <- `HARDWARE_STM32_RX`

参考文件：

- `backend/embodied_arm_ws/src/arm_hardware_bridge/arm_hardware_bridge/stm32_serial_node.py`
- `backend/embodied_arm_ws/src/arm_hardware_bridge/arm_hardware_bridge/hardware_command_dispatcher_node.py`
- `docs/SERIAL_PROTOCOL.md`

## ESP32-S3

上位机默认值已经与拆分后的 ESP32-S3 firmware 对齐：

- launch 默认 endpoint：`http://esp32.local/stream`
- link semantics：`online / mode / stream_endpoint / heartbeat_counter`
- voice event topic 语义：`/arm/voice/events`

参考文件：

- `backend/embodied_arm_ws/src/arm_hardware_bridge/arm_hardware_bridge/esp32_link_node.py`
- `backend/embodied_arm_ws/src/arm_esp32_gateway/arm_esp32_gateway/*`
- `backend/embodied_arm_ws/src/arm_bringup/arm_bringup/launch_factory.py`

## 运行顺序

1. 烧录 STM32F103C8 firmware
2. 烧录 ESP32-S3 firmware 并确认联网
3. 启动 `upper_computer/backend/embodied_arm_ws`
4. 启动 `upper_computer/gateway`
5. 启动 `upper_computer/frontend`

## 注意

`real/hybrid` lane 中相机主链仍然要求上位机收到 `/arm/camera/image_raw`。拆分后的 ESP32 固件保留了 stream endpoint 和板级健康/语音入口，但没有强行伪造真实视觉识别链。这样做是为了不破坏原仓库对 camera/perception runtime 的职责划分。
