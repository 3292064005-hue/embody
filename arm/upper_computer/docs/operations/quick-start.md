# Quick Start

> Audience: developers and integrators
> Owner: project maintainers
> Status: canonical
> Source of Truth: repository Makefiles, runtime authority, gateway/frontend startup scripts
> Last Update Rule: startup commands or minimum environments change together.

> 统一术语引用：本文涉及的 repository validation lane、target runtime lane、preview / validated_sim / validated_live 统一定义见 [`../architecture/terms-and-reference-blocks.md` §2 与 §4](../architecture/terms-and-reference-blocks.md#2-运行时治理术语块)。

## 1. 本文负责什么 / 不负责什么

### 本文负责

- 开发机最短启动路径
- repository validation lane 的最小命令集
- 常见入口的跳转路径

### 本文不负责

- 不定义 runtime 公开语义
- 不定义 API payload
- 不定义 release / HIL 规则

## 2. 适用场景

本文件只回答“怎么在开发机上把系统跑起来并验证基础链路”。它不替代：

- runtime 治理说明
- API contract
- release / HIL 流程

## 3. 环境准备

### Repository validation lane

- Linux
- Python 3.10+
- Node.js 22.x
- npm 10.9.2
- 可在无 ROS2 环境执行仓库级单元/契约/前端/打包门禁

### Target runtime lane

- Ubuntu 22.04 LTS
- ROS 2 Humble
- active overlay / ROS launch 所需依赖

更完整的分层定义见 [`terms-and-reference-blocks.md` §4](../architecture/terms-and-reference-blocks.md#4-验证与发布术语块)。

## 4. 入口选择表

| 你现在要做什么 | 入口 |
|---|---|
| 看系统文档 | `../INDEX.md` |
| 跑仓库级验证 | 本文 §6 |
| 跑 gateway / frontend | 本文 §5 |
| 跑 ROS2 target runtime | `../backend/README.backend.md` 与 `../backend/embodied_arm_ws/README.md` |
| 做固件联调 | `firmware-integration.md` |

## 5. 最短开发路径

### 先看文档

1. `../INDEX.md`
2. `../architecture/system-overview.md`
3. `../architecture/runtime-governance.md`
4. `../interfaces/api-contract.md`

### 启动 backend / gateway / frontend

```bash
# backend / contract / runtime generation
make test-backend-active

# gateway
make test-gateway

# frontend
make test-frontend
make frontend-build
```

如果需要单独运行服务，使用：

```bash
bash scripts/run_gateway.sh
cd frontend && npm ci && npm run dev
```

ROS2 运行入口与 active overlay 构建方式见 `../backend/README.backend.md` 与 `../backend/embodied_arm_ws/README.md`。

## 6. 常见运行模式

- `preview`：用于 contract 验证、链路联调、只读工作台
- `validated_sim`：当前默认公开的 authoritative simulation 主线
- `validated_live`：默认不对外公开，仅保留 promotion / HIL / release slice 语义

统一定义见 [`terms-and-reference-blocks.md` §2](../architecture/terms-and-reference-blocks.md#2-运行时治理术语块)。

## 7. 最小验证集

建议本地至少执行：

```bash
python scripts/generate_contract_artifacts.py --check
python scripts/validate_runtime_contracts.py
pytest -q gateway/tests
python scripts/verify_frontend_validation.py
python scripts/write_frontend_validation_status.py
python scripts/sync_doc_compatibility_mirrors.py --check
python scripts/final_audit.py
```

## 8. 常见问题

### 生成物漂移

先检查 runtime authority 和 generated contracts 是否已同步。

### API / 前端字段不一致

优先检查 `interfaces/api-contract.md`、OpenAPI、generated client 是否同步。

### runtime 表述冲突

以 `runtime-governance.md` 与 generated runtime summary 为准，不以历史 README 或 archive 文档为准。
