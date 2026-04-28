# HIL and Promotion

> Audience: target runtime reviewers, release operators
> Owner: runtime governance / release
> Status: canonical
> Source of Truth: release gate artifacts and validated_live evidence files
> Last Update Rule: validated_live gate requirements change together.

> 统一术语引用：本文涉及的 target runtime lane、HIL / release lane、结果表述规则统一见 [`../architecture/terms-and-reference-blocks.md` §4](../architecture/terms-and-reference-blocks.md#4-验证与发布术语块)。preview / validated_sim / validated_live 的统一定义见 [`../architecture/terms-and-reference-blocks.md` §2](../architecture/terms-and-reference-blocks.md#2-运行时治理术语块)。

## 1. 适用范围

本文件只讲：

- target runtime gate
- HIL smoke / negative path
- validated_live promotion 所需证据

它不替代 `verification-and-release.md`，而是补充说明 validated_live 相关的更高门槛。

## 2. 必需证据

validated_live promotion 至少需要：

- `validated_live_backbone_declared`
- `target_runtime_gate_passed`
- `hil_gate_passed`
- `release_checklist_signed`

缺少任意一项时，public runtime tier 必须继续 fail-closed 为 preview-shaped surface。

## 3. Target runtime gate

target runtime gate 负责证明：

- 目标环境与基线一致
- release slice 所需脚本/工件齐备
- live backbone 声明存在
- promotion 前置条件可被审计

## 4. HIL smoke

至少应覆盖：

- bringup / readiness / command policy 基础检查
- task start / stop 的核心正向路径
- reset fault / recover / maintenance 的闭环
- negative path：缺失条件时是否 fail-closed
- observability 与 execution 是否被正确区分

## 5. Promotion 决策规则

validated_live 的晋升不是“某个 launch 能跑起来”就算完成，而是：

1. 运行时事实源、generated contract、gateway/front 口径一致
2. target runtime gate 通过
3. HIL smoke 与 negative path 通过
4. release checklist 已签署并归档

## 6. 证据归档

所有 validated_live 相关证据必须进入：

- `../evidence/validated_live/`

至少包括：

- smoke report
- target runtime gate report
- release checklist
- 相关说明 README
