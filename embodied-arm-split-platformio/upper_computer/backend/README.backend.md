# ROS2 桌面具身智能机械臂后端（split-stack）

这是当前正式后端主链，不再以旧的 `task_manager + motion_bridge + lifecycle_manager` 作为主架构。

## 正式主链

- `arm_readiness_manager`：统一 readiness 聚合与执行门禁
- `arm_safety_supervisor`：安全监督、停止信号、故障上报
- `arm_task_orchestrator`：任务接入、状态机推进、重试与故障收口
- `arm_scene_manager`：运行期 planning scene 同步与附着状态
- `arm_grasp_planner`：运行期抓取候选生成、排序与回退选择
- `arm_motion_planner`：规划层入口（后续接 MoveIt/MTC/Servo）
- `arm_motion_executor`：阶段执行校验与命令流生成
- `arm_hardware_bridge`：STM32 / ESP32-S3 通信桥接
- `arm_camera_driver` / `arm_perception`：相机采集、目标流与感知收敛主链
- `arm_calibration` / `arm_profiles`：标定与任务/放置配置
- `arm_diagnostics` / `arm_logger`：诊断与日志

## 运行监督层与兼容层

### 运行监督层

- `arm_lifecycle_manager`

该包当前仍承载 `managed_lifecycle_manager_node` / `runtime_supervisor_node`，属于正式运行链的监督基础设施，不再归类为 Runtime Core，也不应继续承接新的业务功能。

### 兼容层

- `arm_task_manager`
- `arm_motion_bridge`

这些旧包只允许：
- 兼容历史入口
- 提供迁移参考
- 支撑旧测试或旧集成

禁止继续向旧包加任何新功能。

## 当前已落实的关键点

- split-stack 默认由 bringup launch 启动
- readiness 与 diagnostics 分离
- 任务编排、规划、执行、硬件桥接边界明确
- 视觉目标与标定链已进入主工作区
- 后端测试默认可运行，不依赖手工补 `PYTHONPATH`

## Validated environment matrix

- OS: **Ubuntu 22.04 LTS**
- ROS 2: **Humble**
- Python: **3.10+**
- Node.js: **22.x**
- npm: **10.9.2**

## 建议构建方式

```bash
cd embodied_arm_ws
colcon build --symlink-install
source install/setup.bash
ros2 launch arm_bringup runtime_sim.launch.py
```


## 目标环境验证

```bash
source /opt/ros/humble/setup.bash
cd embodied_arm_ws
colcon build --symlink-install
source install/setup.bash
pytest -q tests/test_ros_launch_smoke.py tests/test_gateway_dispatcher_feedback_roundtrip.py
```

或在仓库根目录执行：

```bash
make target-env-check
make ros-target-validate
make ros-target-validate-docker
```


Target environment bootstrap (Ubuntu 22.04 only):
```bash
make target-env-bootstrap
make target-env-check
make ros-target-validate
```


## Environment lanes

- Repository validation lane: Linux + Python 3.10+，用于 backend/gateway 契约与单元门禁。
- Target runtime lane: Ubuntu 22.04 + ROS2 Humble + Python 3.10.x，用于 colcon build、runtime_real/runtime_hybrid launch 与 HIL 验收；official_runtime.launch.py 仅保留为 sim lane 兼容别名。
