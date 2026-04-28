# Calibration Versioning

> Audience: backend, vision, operators
> Owner: calibration management
> Status: canonical
> Source of Truth: calibration runtime + generated contract summary + calibration profile topics/services
> Last Update Rule: calibration profile/version semantics must update here when changing profile activation or version payload shape.

## 1. 适用范围

本文件定义 calibration profile 的保存、激活、版本与兼容规则。它不讨论具体标定算法细节，而只定义：

- profile 的生命周期
- active profile 的切换语义
- 版本字段与兼容边界

## 2. 核心模型

每个 calibration profile 一旦保存即视为不可变；系统只允许切换“当前 active profile 指针”，而不是原地改写旧 profile 内容。

这样做的目的：

- 便于回滚
- 便于比较不同 profile
- 避免“同一个 profile id 对应不同内容”的歧义

## 3. Required fields

每个 calibration profile 至少应包含：

- profile id
- workspace transform / offsets
- updated timestamp
- optional notes / quality score

如果系统需要扩展更多字段，应保持向后兼容，并在 generated contract / API / frontend 展示面同步。

## 4. Operations

### Save new profile

保存一个新的 immutable profile，不覆盖旧 profile。

### Activate profile

只切换 active profile 指针。切换应是显式动作，并留下状态 / log / audit 证据。

### Reload / propagate

当 profile 影响 runtime behavior 时，reload 或传播动作必须由对应 backend / gateway 组件显式完成，而不是依赖隐式重载。

## 5. 版本与兼容

- profile payload shape 变化时，应增加版本语义或兼容处理
- frontend 与 gateway 只消费已公开的 profile/version 字段
- 旧 profile 在兼容窗口内必须可读取；是否允许再次激活，由运行时策略决定

## 6. 回滚

回滚方式不是“修改当前 profile”，而是：

1. 选择历史 profile
2. 重新激活历史 profile
3. 记录 active 指针切换与原因
