# Evidence 目录说明

> Status: evidence index
> Scope: `docs/evidence/` reviewer-facing evidence and machine-readable ledger companions

## 1. 目录用途

这里只放验证结果与签收证据，例如：

- smoke report
- validation status / machine-readable ledger
- compatibility regression evidence
- validated_live promotion 相关材料

## 2. 不应放什么

- 运行时规则
- API contract
- readiness / safety 定义
- runtime lane 事实说明

这些内容应写在 canonical 文档，而不是 evidence 文档中。

## 3. 生命周期

证据可以按批次持续累积，但它们不构成当前系统事实源；事实仍以 canonical 文档与 generated contracts 为准。

## 4. 机读证据

当 evidence 既需要给人看，也需要给脚本与审计读时：

- Markdown 负责 reviewer-friendly 摘要
- JSON ledger 负责 machine-readable 聚合
- 二者必须由脚本同源生成，禁止分别手工维护
