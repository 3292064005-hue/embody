# embodied_arm_ws

ROS2 split-stack workspace。

## 1. 先看

- [../../docs/INDEX.md](../../docs/INDEX.md)
- [../../docs/architecture/runtime-governance.md](../../docs/architecture/runtime-governance.md)
- [../../docs/architecture/readiness-and-safety.md](../../docs/architecture/readiness-and-safety.md)
- [../../docs/interfaces/ros2-interface-index.md](../../docs/interfaces/ros2-interface-index.md)

## 2. Workspace 定位

本 workspace 承担：

- bringup / runtime lane launch
- orchestration / planning / execution / bridge 相关 ROS2 包
- readiness、diagnostics、calibration 的 ROS2 状态与接口
- active overlay 下的构建、测试与 launch

## 3. Validated environment matrix

- OS: **Ubuntu 22.04 LTS**
- ROS 2: **Humble**
- Python: **3.10.x**
- Node.js: **22.x**
- npm: **10.9.2**

## 4. 常用启动入口

### Canonical sim lane

```bash
ros2 launch arm_bringup runtime_sim.launch.py
```

### Default runtime entry

```bash
ros2 launch arm_bringup runtime.launch.py runtime_lane:=sim_preview
```

`official_runtime.launch.py` 是 compatibility alias to the `sim_preview` lane，不再承担独立 canonical runtime 语义。

## 5. 当前约束

- runtime 治理唯一可编辑真源：`src/arm_bringup/config/runtime_authority.yaml`
- generated runtime artifacts 由脚本生成，不手改
- active overlay 是默认构建/测试入口
- active task runtime 只允许 split-stack request/result 主链路；`TaskApplicationService.bind_and_plan()` 仅限 compatibility / test-only 场景，并且必须显式 opt-in
- `validated_live` 默认不对外公开；若缺少 promotion evidence，public tier 必须 fail-closed 到 preview

## 6. 与文档系统的关系

本 README 只保留 workspace 局部入口。lane 分类、product line 暴露、promotion gate、公共 readiness surface、API contract 统一以 canonical 文档为准。

## Planner and BT extension contracts

- Motion planner扩展面现在分为三层可审计注册表：`planning_pipeline.py`（pre/post processors）、`providers.py`（scene/grasp providers）、`backend_factory.py`（planning backend plugins）。
- 任务编排 BT 继续保持 fail-closed，但策略树已将 `retry / manual recovery / dispatch readiness` 条件显式写入 `arm_bt_trees/pick_place.yaml`，运行时只负责提供 policy/check 值，不再在主链路里散落隐式分支。
- split-stack planning/execution contract 现在统一携带 `traceEnvelope`，便于 gateway/backend/replay 统一审计。
