# Split Mapping (archived)

> Status: archive
> Replaced by: `../operations/firmware-integration.md`
> Original purpose: 说明 split 后 upper_computer / ESP32 / STM32 的旧映射。

## 现在何时需要读它
- 排查历史 split 设计为何采用当前三仓边界
- 对照旧默认值与旧集成假设

## 当前迁移结论
- 当前固件与上位机集成边界以 `firmware-integration.md` 为准。
- 串口、stream endpoint、联调顺序和默认责任分配不再在本页维护。
