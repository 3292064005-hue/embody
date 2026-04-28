# Runtime Governance

> Audience: gateway, frontend, backend, release
> Owner: runtime governance
> Status: canonical
> Source of Truth: `backend/embodied_arm_ws/src/arm_bringup/config/runtime_authority.yaml`, generated runtime contracts, runtime projection in gateway
> Last Update Rule: changes to lane/public tier/promotion/runtime surface must update runtime authority, generated contracts, this document, and affected gateway/frontend consumers in the same change.

> 统一术语引用：本文涉及的 runtime lane、product line、public runtime tier、runtimeSurfaceState 统一定义见 [`terms-and-reference-blocks.md` §2](terms-and-reference-blocks.md#2-运行时治理术语块)。命令与治理相关术语统一见 [`terms-and-reference-blocks.md` §3](terms-and-reference-blocks.md#3-命令与治理术语块)。

## 1. 本文负责什么 / 不负责什么

### 本文负责

- canonical lane 与 alias 的治理规则
- product line 是否公开、何时 fail-closed
- validated_live promotion 的公开门槛
- runtime public surface 应如何投影到 operator-facing 语义

### 本文不负责

- 不逐字段定义 readiness payload
- 不逐路由定义 REST/WS payload
- 不记录某次验证结果或 smoke 报告

## 2. Runtime lane 是内部命名面，不是公开结论

runtime lane 描述的是 bringup / execution backbone / authority 组合，不等于最终对外公开级别。任何试图通过 launch 名称直接推出“当前就是 validated live”的说法，都是错误的。

## 3. Canonical lanes 与 alias

系统允许存在：

- canonical lanes
- alias lanes
- experimental lanes

要求：

1. alias 只能映射到 canonical lane，不能再额外创造第三份事实定义
2. experimental lane 可以存在，但不自动获得公开 product surface
3. 所有 lane 变化必须经过 runtime authority + generated contracts + gateway/frontend projection 同步

## 4. Product line 与 publiclyExposed

product line 用来回答：“这个运行面是否应该被 operator-facing UI 和公共 API 当作正式支持表面展示”。

判断公开性的关键不是 lane 名称，而是：

- product line 是否 official
- `publiclyExposed` 是否为真
- promotion receipt 是否满足
- fail-closed 条件是否触发

## 5. Public runtime tier

public runtime tier 是 operator-facing 的最终结论。它必须由 gateway/runtime projection 统一投影，不能由前端、README、历史文档各自推断。

典型规则：

- `sim_authoritative` / `full_demo_authoritative` 可公开为 `validated_sim`
- `real_validated_live` 在 promotion 未生效时，public tier 仍必须 fail-closed 为 `preview`

## 6. Promotion 与 release gate

### validated_sim

已具备 baseline promotion receipt，允许作为公开 authoritative simulation 主线。

### validated_live

默认需要以下 marker：

- `validated_live_backbone_declared`
- `target_runtime_gate_passed`
- `hil_gate_passed`
- `release_checklist_signed`

在缺少任意 marker 时：

- product line 不能对外公开
- task workbench 不能互动
- 文档不能写成“真机正式可用”
- public runtime tier 必须继续表现为 preview

更高门槛流程见 [`../operations/hil-and-promotion.md`](../operations/hil-and-promotion.md)。

## 7. 命令治理与运行时入口的一致性要求

本文件不再重复定义 command plane、runtime interface、capability descriptor 的概念，只强调三者的一致性要求：

1. public command plane 必须有对应的 runtime interface
2. runtime interface 的 active/experimental/reserved 状态必须能投影到 gateway 行为
3. capability descriptor 只能补充 operator-facing 描述，不能替代前两者的 gate

具体定义见 [`terms-and-reference-blocks.md` §3](terms-and-reference-blocks.md#3-命令与治理术语块)。

## 8. Runtime public surface

UI 与 operator-facing API 应优先消费 `runtimeSurfaceState`，而不是跨多层直接拼装原始字段。`runtimeSurfaceState` 至少应表达：

- `runtimeTier`
- `runtimeLabel`
- `runtimeBadge`
- `runtimeDeliveryTrack`
- `publicCommandPlanes`
- `observabilityCommandPlanes`
- `runtimeGatewayEntrypoints`
- `activeRuntimeInterfaces`
- `hiddenRuntimeInterfaces`
- `capabilityDescriptorKeys`

## 9. 变更检查表

修改以下内容时，至少同步完成：

| 变更内容 | 至少同步完成 |
|---|---|
| lane / alias / product line | 更新 `runtime_authority.yaml`、重新生成 contracts、更新本文件、更新相关 tests |
| `publiclyExposed` / public tier 规则 | 更新 gateway projection、frontend 消费层、generated summary |
| promotion marker | 更新 `hil-and-promotion.md`、evidence 模板、相关 tests |
| runtimeSurfaceState 结构 | 更新 `api-contract.md`、frontend 消费层、generated contract |
