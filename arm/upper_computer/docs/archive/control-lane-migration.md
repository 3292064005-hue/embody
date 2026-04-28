# Control Lane Migration (archived)

> Status: archive
> Replaced by: `../architecture/runtime-governance.md`
> Original purpose: 记录旧 control lane 到 canonical runtime lane 的迁移。

## 现在何时需要读它
- 排查旧 launch wrapper / alias 仍被谁引用
- 解释为什么某些 live wrapper 需要显式 opt-in

## 当前迁移结论
- canonical lane、alias 和 promotion 规则统一以 `runtime-governance.md` 为准。
- 历史 wrapper 不是新入口；仅在兼容排查时参考。
- retired wrapper 仍要求 `EMBODIED_ARM_ALLOW_LEGACY_LIVE_ALIASES=true` 才能启用。
