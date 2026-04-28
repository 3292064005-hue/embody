# Documentation Index

> Audience: all contributors, reviewers, and release operators
> Owner: project documentation / runtime governance
> Status: canonical
> Source of Truth: `backend/embodied_arm_ws/src/arm_bringup/config/runtime_authority.yaml`, generated runtime contracts, gateway OpenAPI
> Last Update Rule: when runtime governance, public APIs, or release gates change, update this index and the linked canonical documents in the same change set.

本索引是 **upper_computer** 的唯一系统级文档导航入口。任何想要定义系统事实、公共 API、runtime 规则、验证规则的变更，都应先在这里找到对应的 canonical 文档，再修改具体内容；不要在多个 README 或历史文档里重复定义同一事实。

## 1. 文档类型说明

- **canonical**：长期维护、可以手改、定义系统事实与流程。
- **generated**：脚本生成，只读，不手改。
- **evidence**：验证结果、签收记录、promotion 证据，不定义规则。
- **archive**：迁移期或历史文档，仅供参考，不再作为事实源。

术语与重复概念统一引用见：

- [terms-and-reference-blocks.md](architecture/terms-and-reference-blocks.md)

## 2. 新读者从哪里开始

1. [系统总览](architecture/system-overview.md)
2. [Runtime 治理](architecture/runtime-governance.md)
3. [Readiness 与 Safety](architecture/readiness-and-safety.md)
4. [API Contract](interfaces/api-contract.md)
5. [Quick Start](operations/quick-start.md)

## 3. 按场景阅读路径

| 目标 | 建议路径 |
|---|---|
| 快速理解系统 | `system-overview` → `runtime-governance` → `readiness-and-safety` |
| 做前后端联调 | `api-contract` → `readiness-and-safety` → `quick-start` |
| 查发布约束 | `verification-and-release` → `hil-and-promotion` → `evidence/validated_live` |
| 查为什么某能力不公开 | `runtime-governance` → `compatibility-and-deprecation` → generated runtime summary |
| 查历史迁移背景 | `archive/README.md` → 对应 archive 文档 |

## 4. Architecture（系统事实）

- [system-overview.md](architecture/system-overview.md)
  - 项目边界、三大子工程、主链路、默认交付面、职责分层
- [terms-and-reference-blocks.md](architecture/terms-and-reference-blocks.md)
  - 运行时治理、命令治理、验证分层、文档生命周期的统一术语引用块
- [runtime-governance.md](architecture/runtime-governance.md)
  - canonical lane、product line、promotion、runtime surface、fail-closed 规则
- [readiness-and-safety.md](architecture/readiness-and-safety.md)
  - readiness 分层、mode、command policy、runtime interface gate、异常闭环
- [command-lifecycle-and-state-ownership.md](architecture/command-lifecycle-and-state-ownership.md)
  - accepted/completed 语义、状态所有权、主链路责任分段
- [runtime-authority-section-projections.md](architecture/runtime-authority-section-projections.md)
  - authority 拆分 projection、关注点边界、审查入口
- [compatibility-and-deprecation.md](architecture/compatibility-and-deprecation.md)
  - alias、兼容窗口、退役策略
- [calibration-versioning.md](architecture/calibration-versioning.md)
  - calibration profile/version 语义与升级边界

## 5. Interfaces（公共合同）

- [api-contract.md](interfaces/api-contract.md)
  - REST + WebSocket 的唯一权威说明
- [ros2-interface-index.md](interfaces/ros2-interface-index.md)
  - topic / service / action 索引与 owner
- [stm32-serial-protocol.md](interfaces/stm32-serial-protocol.md)
  - 串口帧、命令、状态与错误语义

## 6. Operations（操作流程）

- [quick-start.md](operations/quick-start.md)
  - 开发/联调最短路径
- [firmware-integration.md](operations/firmware-integration.md)
  - 上位机与 ESP32/STM32 的职责与联调顺序
- [verification-and-release.md](operations/verification-and-release.md)
  - 测试分层、release gate、证据边界
- [hil-and-promotion.md](operations/hil-and-promotion.md)
  - HIL smoke、negative path、validated_live promotion

## 7. Generated（只读生成物）

- [runtime_contract_summary.md](generated/runtime_contract_summary.md)
- [runtime_acceptance_matrix.md](generated/runtime_acceptance_matrix.md)
- [generated/README.md](generated/README.md)

这些文件只用于阅读，不应手工修改。若生成物与 canonical 文档不一致，应修改事实源或生成脚本，再重新生成。legacy 文档若被脚本或迁移消费者继续依赖，应优先收敛为 generated compatibility mirror，而不是继续保留 pointer 页面。顶层 `docs/` 默认只保留 `INDEX.md` 与少量机器消费的 generated compatibility mirrors；其余说明应放入分层目录。

## 8. Evidence（结果与签收）

- [compatibility-regression.md](evidence/compatibility-regression.md)
- [frontend-validation-status.md](evidence/frontend-validation-status.md)
- [validated_live/README.md](evidence/validated_live/README.md)
- [evidence/README.md](evidence/README.md)

## 9. Archive（历史/迁移）

- [archive/README.md](archive/README.md)

archive 里的文档可以帮助理解迁移背景，但不再作为当前系统事实源。任何事实型修改都应落在 canonical 文档，而不是 archive 文档。

## 10. 变更影响映射

| 变更内容 | 首先改哪里 | 至少连带检查 |
|---|---|---|
| runtime lane / product line / promotion | `architecture/runtime-governance.md` | generated runtime summary、gateway/frontend 投影、相关 tests |
| readiness 字段 / command gate / runtime interface | `architecture/readiness-and-safety.md` | `interfaces/api-contract.md`、gateway tests |
| REST / WS payload | `interfaces/api-contract.md` | OpenAPI、frontend 消费、generated contract |
| 快速启动步骤 / 环境基线 | `operations/quick-start.md` | 根 README、upper_computer README、相关 README |
| release / validation / evidence 规则 | `operations/verification-and-release.md` | `operations/hil-and-promotion.md`、`evidence/`、JSON ledger |
| 兼容窗口 / 退役策略 | `architecture/compatibility-and-deprecation.md` | archive pointer 文档、generated summary |

## 11. 修改规则

- 修改系统事实：先改 canonical 文档，再同步代码/配置/生成物
- 修改 generated：不要手改，改事实源并重新生成
- 新增验证结果：放到 evidence；需要机读时同步生成 ledger
- legacy 路径若仍被脚本消费：优先生成 compatibility mirror，不要只留 pointer
- 迁移期说明：放到 archive
- 不允许再新增第二份“定义同一事实”的 README 或专题文档
