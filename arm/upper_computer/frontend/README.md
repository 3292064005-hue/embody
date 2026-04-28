# Frontend / HMI

Vue 3 + Pinia + Element Plus 的操作与观测前端。

## 1. 先看

- [../docs/INDEX.md](../docs/INDEX.md)
- [../docs/interfaces/api-contract.md](../docs/interfaces/api-contract.md)
- [../docs/architecture/runtime-governance.md](../docs/architecture/runtime-governance.md)
- [../docs/architecture/readiness-and-safety.md](../docs/architecture/readiness-and-safety.md)
- [docs/testing.md](docs/testing.md)

## 2. 前端职责

前端负责：

- public runtime surface 的可视化表达
- command policy / mode / readiness 的操作提示
- command receipt、log、diagnostics 的 operator-facing 展示
- 对 targets/frame/hardware/task 的 runtime snapshot 消费

前端不负责重新定义：

- runtime lane 真假
- validated_live 是否可公开
- command plane contract
- release / HIL gate

这些都由 gateway projection 和 canonical 文档提供。

## 3. 环境与运行

### Environment contract

- Node.js: **22.x**
- npm: **10.9.2**
- 建议主机 OS: **Ubuntu 22.04 LTS**

### 安装与启动

```bash
npm ci
cp .env.example .env
npm run dev
```

## 4. 构建与检查

```bash
npm run typecheck
npm run typecheck:test
npm run test:unit
npm run build
```

> 以上命令用于前端本地检查；若需要生成仓库级可审计 evidence，请在仓库根目录执行 `python scripts/verify_frontend_validation.py`，再运行 `python scripts/write_frontend_validation_status.py`。

## 5. 当前前端消费原则

- public runtime 语义优先消费 `runtimeSurfaceState`
- 详细 command/rule 语义消费 `commandPlanes` 与 `commandPolicies`
- API 字段与 websocket 事件以 gateway canonical contract 为准
- capability descriptor 已进入维护页展示，但不会独立推翻 gateway/runtime 的 truth

## 6. 文档边界

本 README 不再重复系统级 runtime / readiness / promotion 事实；这些内容统一在 `../docs/` 的 canonical 文档中维护。
