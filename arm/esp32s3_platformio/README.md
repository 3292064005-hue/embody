# ESP32-S3 PlatformIO Firmware

该固件承接原项目中的 ESP32 相关语义，而不是随意新造一套协议。

## 对应原仓库模块

- `upper_computer/backend/embodied_arm_ws/src/arm_hardware_bridge/arm_hardware_bridge/esp32_link_node.py`
- `upper_computer/backend/embodied_arm_ws/src/arm_esp32_gateway/arm_esp32_gateway/board_health_parser.py`
- `upper_computer/backend/embodied_arm_ws/src/arm_esp32_gateway/arm_esp32_gateway/voice_event_client.py`
- `upper_computer/backend/embodied_arm_ws/src/arm_esp32_gateway/arm_esp32_gateway/status_notifier.py`
- `upper_computer/backend/embodied_arm_ws/src/arm_bringup/arm_bringup/launch_factory.py`

## 保留的关键细节

- 默认 hostname：`esp32.local`
- 默认 stream endpoint：`http://esp32.local/stream`
- 保留 board health / online / mode / heartbeat_counter / camera_serial 语义
- 保留 voice event 扩展语义，对齐 `/arm/voice/events`
- Wi‑Fi transport 与 HTTP server 承接 `gateway.yaml` 中 `transport: wifi`

## HTTP API

- `GET /healthz`
- `GET /status`
- `GET /stream`
- `GET /voice/events`
- `POST /voice/phrase`
- `GET /voice/commands`

### 示例

```bash
curl http://esp32.local/healthz
curl http://esp32.local/status
curl -X POST http://esp32.local/voice/phrase -d '{"phrase":"start"}'
```

## 串口控制台

USB CDC/串口监视器里输入一行文本并回车，也会被记录成 voice phrase，便于没有本地语音模型时联调上位机事件链。

## 注意

这份 generic ESP32-S3 固件默认通过 authority 生成的 `preview_reserved` profile 把 `/stream` 定义为**reserved metadata/control-plane endpoint**：

- 默认 `runtime semantic profile=preview_reserved`
- 默认 `stream_semantic=reserved`
- 默认 `frame_ingress_live=false`
- 默认 `delivery_model=control_plane_only`
- `/stream` 不直接承诺板端 MJPEG 传输，也不把 generic firmware 伪装成 live ingress

若你的板卡需要对齐其他 runtime lane，可通过 PlatformIO `build_flags` 覆盖 `EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE`：

- `EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE=EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE_PREVIEW_RESERVED`
- `EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE=EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE_VALIDATED_SIM_SYNTHETIC`
- `EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE=EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE_VALIDATED_LIVE_EXTERNAL_BRIDGE`

生成头文件位于 `include/generated/runtime_semantic_profile.hpp`，由 `upper_computer/scripts/sync_runtime_authority.py` 自动产出。
