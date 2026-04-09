# validated_live Promotion Gate

`validated_live` 不是配置项写成 `true` 就自动生效的 lane。当前仓库的唯一能力真源是 `backend/embodied_arm_ws/src/arm_bringup/config/runtime_authority.yaml`，其生成出的运行时文件会把晋升条件收口为以下四项同时满足：

1. `validated_live_backbone_declared=true`：canonical backbone 同时声明了 live planning backend、ros2_control execution backbone、live vision ingress 与 hardware command path
2. `target_runtime_gate_passed=true`：`artifacts/release_gates/target_runtime_gate.json` 中 target-runtime gate 已达到 `passed`
3. `hil_gate_passed=true`：`validated_live_evidence.yaml` 中 HIL 证据为 `passed`，且对应 artifact 已存在
4. `release_checklist_signed=true`：`validated_live_evidence.yaml` 中 release checklist 证据为 `passed`，且对应 artifact 已存在

这样做的目的，是把“技术上可连通”和“工程上可交付”拆开，避免把预留真机链误当成已正式开放的交付能力。

## 回滚

若 live lane 在 HIL 或现场验证中失败，只需：

- 将 `runtime_authority.yaml` / `runtime_promotion_receipts.yaml` 中 `validated_live.promoted` 改回 `false`
- 或者把 `validated_live_evidence.yaml` 中任一 gate 相关证据改回非 `passed`
- 保持 `validated_sim` 继续作为当前正式 authoritative lane

该回滚不会影响 `validated_sim`、Gateway、HMI、日志与审计链。

## 同步方式

修改 live / sim 能力矩阵时，先编辑 `runtime_authority.yaml`，再执行：

```bash
python scripts/sync_runtime_authority.py
python scripts/generate_contract_artifacts.py
```

若要更新 target-runtime gate / release evidence，则执行：

```bash
make verify-repo
make target-gate
```

`make target-gate` 会同时刷新 `artifacts/release_gates/target_runtime_gate.json` 与 `artifacts/release_gates/release_evidence.json`。
