# Embodied Arm — Split Delivery (Upper Computer / ESP32-S3 / STM32F103C8)

本交付把原始一体化仓库拆成三部分，同时保留原项目中的协议、状态字段、命令语义、启动默认值与文档：

- `upper_computer/`：上位机，保留原始 `frontend + gateway + backend/embodied_arm_ws + docs + scripts` 运行形态
- `esp32s3_platformio/`：ESP32-S3 PlatformIO 固件，承接原项目中的 Wi‑Fi / stream endpoint / board health / voice event 扩展语义
- `stm32f103c8_platformio/`：STM32F103C8 PlatformIO 固件，承接原项目中的串口帧协议、ACK/NACK、REPORT_STATE、REPORT_FAULT 与执行语义

## 保留的原项目关键细节

### 上位机
- 保留原始目录与启动方式：`frontend/`、`gateway/`、`backend/embodied_arm_ws/`
- 保留原始 runtime lane 约束与兼容别名：
  - `stm32_port=/dev/ttyUSB0`
  - `esp32_stream_endpoint=http://esp32.local/stream`
  - `real_preview/hybrid_preview` 相机链仍由 `/arm/camera/image_raw` 进入上位机
  - 历史 `sim/real/hybrid/hw/full_demo` 名称仍可用，但都会映射到新的 `*_preview` canonical lanes
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
- 保留 Wi‑Fi transport、stream endpoint、board health、voice event 的原始语义；但当前 `/stream` 默认为 reserved endpoint，不伪装成真实视觉帧链

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
  - 当前执行语义仍以协议联调/状态推进为主，不应直接表述成已验证真机执行控制器
  - runtime lane 现已显式外置 `forward_hardware_commands / hardware_execution_mode`，避免任务执行链在 authoritative lane 中停留在假闭环

## 推荐使用顺序

1. 先在 `upper_computer/` 跑 `runtime_sim.launch.py` 或 `official_runtime.launch.py` 验证默认 **preview / contract-only** 仿真链路
2. 再烧录 `stm32f103c8_platformio/`，接入 `/dev/ttyUSB0`
3. 再烧录 `esp32s3_platformio/`，确认 `http://esp32.local/stream` 与 `/healthz`；注意 `/stream` 当前只代表 reserved endpoint 语义
4. 最后把上位机 runtime lane 切到 `hybrid_preview/real_preview`（历史 `hybrid/real` 名称仍可用）
5. 若已接好 live planning backend 与真实硬件反馈链，再使用 `runtime_real_authoritative.launch.py` 进入 `real_authoritative`；若 backend 未声明或 readiness 不通过，系统保持 preview-tier 且禁止交互式 task 执行

更细的映射与集成说明见 `docs/split_mapping.md`。

> 当前默认 `*_preview` lane 不提供 authoritative planning，也不会把 task execution 转发到硬件 dispatcher；maintenance/manual 控制仍按独立命令策略运行。
> 若需要仓内已验证的 authoritative simulation 主线，可切换到 `sim_authoritative` 或 `full_demo_authoritative`，此时 `motion_executor -> dispatcher -> feedback(command_id)` 主链路会显式打开；scene/grasp provider 仍维持 embedded-core，`ros2_control` 仍不计入正式 execution authority。
> 若接入真实相机/串口链并显式提供 live planning backend，可切到 `real_authoritative`；该 lane 对 live backend 采用 fail-closed 语义，不会降级为 fallback contract。


## 根级验证与打包

- `make verify`：运行 split 仓库正式质量门：包含 upper_computer fast gate、离线 firmware source contract 校验；若本机已预装对应 PlatformIO platform 包，则继续执行 ESP32/STM32 实际编译，否则把真实固件编译留给 CI 或联网工作站。
- `make package`：生成根级 release manifest 与压缩包。


> HMI task workbench is now capability-driven: preview lanes keep task execution read-only, while authoritative lanes expose the full workbench.

## 第三方治理

- 根级 `LICENSE`：仓库自有代码授权声明
- `THIRD_PARTY_NOTICES.md`：第三方参考与后续 vendoring 规则
- `third_party/UPSTREAM_INDEX.md`：上游来源索引
- `scripts/verify_third_party_governance.py`：治理完整性校验
