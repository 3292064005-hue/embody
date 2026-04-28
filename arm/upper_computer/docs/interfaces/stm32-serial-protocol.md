# STM32 Serial Protocol

> Audience: backend, firmware, integration
> Owner: hardware bridge / firmware protocol
> Status: canonical
> Source of Truth: STM32 firmware implementation + backend protocol adapters + this document
> Last Update Rule: frame format, command IDs, payload semantics, or fault/report structure changes must update firmware and backend in the same change.

本协议文档以当前代码实现为准，对齐以下权威实现：

- `backend/embodied_arm_ws/src/arm_backend_common/arm_backend_common/enums.py`
- `backend/embodied_arm_ws/src/arm_backend_common/arm_backend_common/protocol.py`
- `../stm32f103c8_platformio/include/protocol.hpp`
- `../stm32f103c8_platformio/src/protocol.cpp`
- `../stm32f103c8_platformio/src/main.cpp`

## 1. 协议定位

串口协议负责把 gateway / dispatcher 层的硬件命令，映射为 STM32 可消费的帧与状态回包。它的目标是：

- 帧结构稳定
- ACK/NACK 明确
- 故障/状态有清晰上报
- simulated transport 与 live transport 的行为边界清楚

## 2. 帧格式

- SOF: `0xAA55`
- 固定头：版本、命令、长度
- payload：按命令定义
- 校验：以 firmware / backend 共同实现为准

如果帧结构变化，必须同步修改 firmware 与 backend，不能单边先改。

## 3. 命令分类

至少应覆盖：

- stop / emergency / recover 类
- home / reset fault 类
- jog / gripper / servo cartesian 类
- 运行时必要的 simulated transport 命令投影

对外语义必须与 gateway 的 `manual_control` / `system_control` plane 保持一致；串口层不应偷偷引入新的 operator-facing 命令分类。

## 4. 回包语义

回包至少区分：

- ACK：命令已接受
- NACK：命令被拒绝
- state report：状态更新
- fault report：故障上报

failure 原因必须能在 backend/gateway 层映射成统一 failure class 或 human-readable message。

## 5. 超时与重试

超时、重试、重入控制由 backend bridge 与 firmware 共同决定；若其中一端改变策略，应同步更新本文件与实现，避免“文档写一个、代码跑另一个”。

## 6. Simulated transport 与 live transport

当前仓库同时支持 simulated transport 语义。要求：

- simulated transport 必须诚实标注，不能装成真实硬件已执行
- live transport 的权威性不能由 simulated fallback 伪装出来
- 新增命令（例如 `SERVO_CARTESIAN`）必须同时考虑 simulated 路径是否具备最小兼容处理

## 7. 修改流程

修改串口协议时，至少同步完成：

1. firmware 实现
2. backend protocol / bridge 适配
3. 本文档
4. 相关测试与 release evidence

## 8. Legacy compatibility mirror

旧路径 `../SERIAL_PROTOCOL.md` 保留为 generated compatibility mirror，供 firmware/source gate 与迁移消费者读取；本文件继续承担 canonical 叙述职责。
