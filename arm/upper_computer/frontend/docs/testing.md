# Frontend Testing

> Status: local frontend guide
> Canonical release rules: `../../docs/operations/verification-and-release.md`

## 1. 本地检查

```bash
npm ci
npm run typecheck
npm run typecheck:test
npm run test:unit
npm run build
```

## 2. 覆盖重点

### Unit

- `domain/safety/guards.test.ts`
  - readiness / role / mode 对命令门禁的影响
- `stores/readiness` / `stores/receipt`
  - runtime surface、receipt、投影事件消费

### Build-time contract

- generated client 的类型约束
- `runtimeSurfaceState` / readiness 模型与页面消费的一致性
- canonical API contract 变更后，前端是否同步更新

## 3. 不应做的事

- 在前端重新定义一套 API contract
- 在 UI 层推翻 gateway/runtime 的 authoritative truth
- 用测试 mock 把 preview 写成 validated live

## 4. 与系统级验证的关系

前端测试只覆盖前端消费与构建边界；release / HIL / target runtime gate 的规则统一以 `../../docs/operations/verification-and-release.md` 为准。
