# Split Mapping

## 1. Upper Computer

原始仓库整体保留在 `upper_computer/`，没有做“伪 PlatformIO 化”。原因是：

- 上位机包含 Python / ROS2 / FastAPI / Vue3
- PlatformIO 适合 MCU/firmware，不适合承载 ROS2 workspace、Gateway、Frontend
- 强行改成 PlatformIO 目录会破坏原项目的实际运行形态与脚本入口

因此，上位机部分保留原项目真实可运行结构，避免为了“看起来统一”而破坏原架构。

## 2. ESP32-S3 映射

原项目中的 ESP32 语义来源：

- `arm_hardware_bridge/esp32_link_node.py`
- `arm_esp32_gateway/esp32_gateway_node.py`
- `arm_esp32_gateway/board_health_parser.py`
- `arm_esp32_gateway/voice_event_client.py`
- `arm_esp32_gateway/status_notifier.py`
- `arm_bringup/launch_factory.py` 中 `esp32_stream_endpoint=http://esp32.local/stream`

拆分后，ESP32-S3 firmware 负责：

- 板级联网与在线状态
- stream endpoint 占位/扩展入口
- board health HTTP 输出
- voice phrase 采集与回放
- `camera_serial`、`heartbeat_counter`、`mode` 等元数据

## 3. STM32F103C8 映射

原项目中的 STM32 语义来源：

- `docs/SERIAL_PROTOCOL.md`
- `arm_backend_common/protocol.py`
- `arm_backend_common/enums.py`
- `arm_hardware_bridge/stm32_serial_node.py`
- `arm_hardware_bridge/hardware_command_dispatcher_node.py`
- `arm_hardware_bridge/hardware_state_aggregator_node.py`

拆分后，STM32 firmware 负责：

- 115200 UART 帧协议
- CRC16 校验
- ACK/NACK/REPORT_STATE/REPORT_FAULT
- 去重窗口内命令幂等
- HOME/STOP/GRIPPER/EXEC_STAGE/JOG/SERVO/RESET_FAULT/QUERY_STATE 执行语义
- 周期性状态上报

## 4. 集成默认值

- STM32 串口默认：`/dev/ttyUSB0`
- ESP32 stream endpoint 默认：`http://esp32.local/stream`
- `real/hybrid` 仍要求上位机视觉链向 `/arm/camera/image_raw` 注入图像
- Gateway 与 ROS2 仍通过 `upper_computer/` 中原脚本与 launch 文件启动
