# Firmware Integration

> Audience: backend, firmware, system integration
> Owner: hardware integration
> Status: canonical
> Source of Truth: split mapping, firmware READMEs, backend bridge/runtime authority
> Last Update Rule: firmware responsibilities, endpoints, or protocol ownership change together.

> 统一术语引用：本文涉及的 command plane、runtime interface、observability plane 统一定义见 [`../architecture/terms-and-reference-blocks.md` §3](../architecture/terms-and-reference-blocks.md#3-命令与治理术语块)。

## 1. 目标

说明上位机与两块固件的职责边界、通信链路以及联调顺序。

## 2. Split 映射

### ESP32-S3

当前承接：

- Wi-Fi / endpoint reachability
- board health
- metadata bridge
- voice / observability 扩展语义

不应把 ESP32 当前能力写成独立 authoritative execution backbone。

### STM32F103C8

当前承接：

- 串口协议
- ACK/NACK
- 状态 / 故障上报
- dispatcher 对接的执行与 simulated transport 兼容语义

## 3. 上位机到固件的链路

典型链路为：

`gateway -> ROS2 backend -> dispatcher / bridge -> firmware protocol / transport -> firmware`

其中：

- Gateway 负责公共入口与治理
- backend 负责执行主链与桥接
- firmware 负责板级执行与状态上报

## 4. ESP32 集成要点

- 数据面与观测面必须诚实描述为当前 profile 支持的能力
- voice / frame / metadata ingress 需要经过 runtime interface 或 ingress policy gate
- observability-only 事件不能被文档包装成 execution command

## 5. STM32 集成要点

- command 映射必须与 gateway command plane 保持一致
- protocol 变化必须同步 backend 与 firmware
- simulated transport 存在时，必须显式标注，不得冒充真实硬件执行结果

## 6. 联调顺序

1. 确认 generated contracts 与 runtime authority 一致
2. 先跑 backend / gateway / frontend 的仓库级验证
3. 再做 ROS2 launch / bridge 联调
4. 最后接入 ESP32 / STM32 实机或 target runtime 环境

## 7. 故障定位入口

- runtime truth / lane 问题：`../architecture/runtime-governance.md`
- readiness / command gate 问题：`../architecture/readiness-and-safety.md`
- API 与 public surface 问题：`../interfaces/api-contract.md`
- 串口协议问题：`../interfaces/stm32-serial-protocol.md`

## 8. Legacy compatibility mirror

旧路径 `../FIRMWARE_SPLIT_INTEGRATION.md` 保留为 generated compatibility mirror，供 split repository gate 与迁移消费者读取；本文件继续承担 canonical 叙述职责。
