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
- link semantics：`online / mode / stream_endpoint / heartbeat_counter / stream_semantic / stream_reserved / frame_ingress_live`
- REST 路由：`/healthz`、`/status`、`/stream`、`/voice/events`、`/voice/commands`、`/voice/phrase`
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

`real/hybrid` lane 中相机主链仍然要求上位机收到 `/arm/camera/image_raw（标准 sensor_msgs/Image）`。拆分后的 ESP32 固件保留了 stream endpoint 和板级健康/语音入口，但没有强行伪造真实视觉识别链。当前默认语义为：

- `stream_semantic=reserved`
- `stream_reserved=true`
- `frame_ingress_live=false`

这意味着：

- `/stream` 只说明板级 endpoint 预留存在；
- ESP32 在线不等价于 camera ingress live；
- 上位机 gateway/frontend 会把 ESP32 在线与 frame ingress 状态分开展示。


## validated_live / live_control / real_validated_live lanes

`live_control` 用于真实相机 + 真串口候选链路，`real_validated_live` 用于 promotion-gated validated live 链路。两者共享以下硬约束：

历史 `real_authoritative` 入口现在只作为 `live_control` 的兼容 alias，不能再作为独立 live lane 维护。

- `planning_capability=validated_live`
- `planning_backend_name=validated_live_bridge`
- `planning_backend_profile=validated_live_bridge`
- 没有 live planning backend 时 fail-closed，不允许自动回退到 `fallback_contract`
- `hardware_execution_mode=ros2_control_candidate`
- `forward_hardware_commands=true`
- 相机链语义从 reserved endpoint 提升为 `live_camera_stream`，但 `/stream` 仍只承载 ESP32 authoritative metadata/control-plane，真实帧传输由 external camera bridge 提供
- live backend 声明默认从 `src/arm_bringup/config/planning_backend_profiles.yaml` 读取，也可通过 `EMBODIED_ARM_PLANNING_BACKENDS_FILE` 外置覆盖
- lane 晋升还必须依赖 `src/arm_bringup/config/runtime_promotion_receipts.yaml` 中的 `validated_live.promoted=true`，否则继续 fail-closed

这意味着：

- `motion_executor` 会把 `ros2_control_live` 视为强约束 transport，并通过 ros2_control trajectory/action 主链提交执行目标；
- live lane 下如果关闭 `forward_hardware_commands`，或 ros2_control backbone 未声明，执行链会被显式拒绝，而不是静默 shadow；
- `/stream` 只负责表述 frame ingress 语义，不能替代上位机视觉主链。
- 历史 `/arm/camera/image_raw_compat` JSON 入口默认不会再自动回灌标准 `/arm/camera/image_raw`，避免兼容链把同一帧重复投影到 perception；只有显式打开 `republish_compat_frames_as_standard_image=true` 才允许回灌。

## Runtime safety authority

`src/arm_bringup/config/safety_limits.yaml` 已从发布期镜像校验物提升为运行时 safety authority：

- `motion_executor` 会在执行目标进入队列前校验 joint limits / gripper force / execution target；
- `hardware_command_dispatcher` 会在串口帧下发前校验 `SERVO_CARTESIAN`、`JOG_JOINT` 与 gripper force；
- Gateway jog/servo 输入限制与后端共用同一份 authority，避免前后端阈值漂移。
- Gateway 运行时配置加载器现在按文件签名自动刷新；`/api/system/readiness` 会同时投影 `manualCommandLimits` 与 `runtimeConfigVersion`，前端维护页优先消费运行时回传限制，生成契约只作为冷启动回退。
