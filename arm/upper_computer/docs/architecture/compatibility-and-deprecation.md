# Compatibility and Deprecation

> Audience: maintainers, reviewers, release owners
> Owner: architecture / compatibility governance
> Status: canonical
> Source of Truth: generated runtime contracts, compatibility aliases, deprecation decisions recorded in code and release docs
> Last Update Rule: add/update this file when compatibility aliases or public fields enter/leave the support window.

> 统一术语引用：本文涉及的 runtime alias、兼容字段、canonical / generated / evidence / archive 生命周期统一定义见 [`terms-and-reference-blocks.md` §2 与 §5](terms-and-reference-blocks.md#2-运行时治理术语块)。

## 1. 文档目的

本文件定义：

- 什么属于兼容面
- 什么允许临时保留
- 什么必须进入退役窗口
- 怎样避免兼容层变成新的事实源

## 2. 兼容面分类

### Runtime aliases

兼容 alias 允许旧入口在过渡期继续工作，但必须满足：

- alias 只映射到 canonical lane
- alias 不得拥有独立语义
- alias 必须在 generated artifact 中显式声明

### Compatibility fields

这类字段允许继续输出一段时间，但 canonical 文档只定义语义字段，不再以 compatibility field 作为主要表述。

当前典型 alias：

- `allReady -> modeReady`
- `mode -> runtimePhase`
- `operatorMode -> controllerMode`
- `currentStage -> taskStage`

### Compatibility wrappers / migration docs

旧 launch wrapper、旧索引文档、迁移说明可以保留，但应放在 archive 或显式 compatibility 层，不能继续承担当前事实定义。

## 3. 退役策略

兼容项进入退役窗口的前提包括：

- canonical 替代物已经稳定存在
- 代码、合同、前端消费方已迁移
- release 与 evidence 文档已说明迁移影响

退役分三步：

1. 标记 deprecated
2. 只读兼容 / 不再扩展
3. 删除并记录到 archive

## 4. 当前应保留的兼容层

- runtime lane aliases
- compatibility launch wrappers
- 旧文档跳转页（仅保留 pointer）
- 某些 public response 中的旧字段（若仍被消费）

## 5. 当前不应扩散的旧面

- 在 README 中重新定义 runtime tier / product line
- 在前端另写一套 API contract
- 在 Gateway 或 docs 中新增第二套 readiness/mode 语义名

## 6. 归档原则

以下内容应进入 archive，而不是继续停留在主入口层：

- 迁移期说明
- 阶段性 alignment 文档
- 已被 canonical 文档取代的专题文档
- 历史性 support/deprecation matrix

## 7. 变更约束

新增兼容层时，必须同时回答：

- 它的 canonical 替代物是什么
- 它打算保留多久
- 它最终如何退役
- 哪份 evidence / checklist 会验证迁移完成
