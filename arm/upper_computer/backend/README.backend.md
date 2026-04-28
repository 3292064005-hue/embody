# Backend / ROS2 Workspace

本目录承载 `embodied_arm_ws` 及其构建、测试、运行入口。

## 1. 应先阅读的文档

- [../docs/INDEX.md](../docs/INDEX.md)
- [../docs/architecture/system-overview.md](../docs/architecture/system-overview.md)
- [../docs/architecture/runtime-governance.md](../docs/architecture/runtime-governance.md)
- [../docs/interfaces/ros2-interface-index.md](../docs/interfaces/ros2-interface-index.md)

## 2. Backend 在系统中的职责

backend 负责上位机执行主链的 ROS2 部分：

- task orchestration
- motion planning
- motion execution
- dispatcher / bridge / hardware IO
- readiness / diagnostics / calibration 的 ROS2 侧权威状态

需要特别注意：

- backend 不单独定义 public runtime tier
- backend 的可公开语义由 `runtime_authority.yaml` + generated contracts + gateway projection 共同决定
- backend README 不应重复定义前端/Gateway 的 API 与 UI 暴露规则

## 3. Validated environment matrix

- OS: **Ubuntu 22.04 LTS**
- ROS 2: **Humble**
- Python: **3.10.x**
- Node.js: **22.x**
- npm: **10.9.2**

## 4. 常用操作

### Active overlay build

```bash
ACTIVE_OVERLAY=$(python ../scripts/materialize_active_ros_overlay.py --print-root)
ACTIVE_PACKAGES=$(python ../scripts/print_active_ros_packages.py)
cd "$ACTIVE_OVERLAY"
colcon build --symlink-install --packages-up-to $ACTIVE_PACKAGES
source install/setup.bash
```

### 默认运行入口

```bash
ros2 launch arm_bringup runtime.launch.py runtime_lane:=sim_preview
```

### 常用验证

```bash
python ../scripts/check_active_profile_consistency.py
python ../scripts/check_deprecated_runtime_usage.py
python ../scripts/validate_runtime_contracts.py
pytest -q ../gateway/tests
```

## 5. backend 文档边界

本 README 只保留 backend 局部入口，不再重复：

- 完整 runtime lane 定义
- validated_live promotion 规则
- readiness / safety 公共字段
- REST / WebSocket contract

这些内容统一由 `../docs/` 中的 canonical 文档维护。
