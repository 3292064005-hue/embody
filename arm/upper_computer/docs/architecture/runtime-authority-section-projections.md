# Runtime Authority Section Projections

> Audience: implementers / reviewers / release operators
> Owner: runtime governance
> Status: canonical
> Source of Truth: `backend/embodied_arm_ws/src/arm_bringup/config/runtime_authority.yaml` and generated section projections
> Last Update Rule: when authority concern boundaries or generated section files change, update this document and the sync script together.

## 1. 目的

`runtime_authority.yaml` 仍是唯一可编辑真源，但为了降低审查成本，本仓库现在会额外生成按关注点拆分的 projection：

- `config/runtime_authority_sections/product_lines.yaml`
- `config/runtime_authority_sections/command_planes.yaml`
- `config/runtime_authority_sections/capability_registry.yaml`
- `config/runtime_authority_sections/task_catalog_contract.yaml`
- `config/runtime_authority_sections/runtime_governance.yaml`

这些文件都由 `scripts/sync_runtime_authority.py` 生成，**只读，不手改**。

## 2. 为什么要拆

单个 authority 文件同时承载：

- product line 暴露面
- runtime governance
- command plane 治理
- capability registry
- task catalog contract

这会让评审一个小变更时必须重新打开整份大文件。拆分 projection 后：

- reviewer 可以只看相关 concern 的 diff
- 测试可以更精确地检查 drift
- 前端/网关后续若只需某一投影，可避免继续耦合 full authority 结构

## 3. 边界规则

- `runtime_authority.yaml`：唯一可编辑真源
- `runtime_authority_sections/*.yaml`：只读 section projection，当前已被 `scripts/generate_contract_artifacts.py` 与 `arm_bringup/launch_factory.py` 直接消费；新增消费者只能读取 projection，不得反向绕回 hand-maintained section truth
- 已存在的 `runtime_profiles.yaml` / `task_capability_manifest.yaml` 等仍保留，因为它们是运行时/合同投影，不是简单 section mirror

## 4. 变更影响矩阵

| 你改什么 | 至少检查什么 |
|---|---|
| `product_lines` | `runtime_authority_sections/product_lines.yaml`、generated runtime contracts、frontend runtime surface |
| `command_planes` | `runtime_authority_sections/command_planes.yaml`、gateway command contracts、receipt/audit 测试 |
| `capability_registry` | `runtime_authority_sections/capability_registry.yaml`、runtime interface gate、generated contract |
| `task_catalog_contract` | `runtime_authority_sections/task_catalog_contract.yaml`、task manifest、frontend task center |
| `runtime_governance` | `runtime_authority_sections/runtime_governance.yaml`、`scripts/generate_contract_artifacts.py`、`arm_bringup/launch_factory.py`、release gate tests |
