# ROS2 Interface Index

> Audience: backend, gateway, integration
> Owner: ROS2 interface governance
> Status: canonical
> Source of Truth: generated runtime contract summary + interface definitions in `arm_interfaces`
> Last Update Rule: topic/service/action changes must update generated contracts and this index together.

> Generated reference inputs: `arm_common/topic_names.py`, `service_names.py`, `action_names.py`, `arm_bringup/launch_factory.py`.

## 1. 使用方式

本文件回答三个问题：

1. 某个公共 ROS2 topic/service/action 的名字是什么
2. 它属于哪类接口（public / compatibility / internal / experimental）
3. 谁拥有它、谁消费它

如果你想知道 REST/WS 层怎么暴露这些接口，请看 `interfaces/api-contract.md`；本文件只讨论 ROS2 边界本身。

## 2. Public ROS 2 topics

### Runtime / readiness / diagnostics

- `/arm/bringup/status`
- `/arm/bringup/status_typed`
- `/arm/readiness/state`
- `/arm/readiness/state_typed`
- `/arm/diagnostics/health`
- `/arm/diagnostics/summary_typed`
- `/arm/log/event`

### Hardware / system

- `/arm/hardware/state`
- `/arm/system/state`
- `/arm/fault/report`

### Vision / calibration / task

- `/arm/camera/frame_summary`
- `/arm/camera/health`
- `/arm/camera/image_raw`
- `/arm/camera/camera_info`
- `/arm/vision/summary`
- `/arm/vision/target`
- `/arm/vision/targets`
- `/arm/vision/targets_typed`
- `/arm/calibration/profile`
- `/arm/calibration/profile_typed`
- `/arm/task/status`
- `/arm/task/status_typed`

## 3. Services

### Operator-facing / gateway-relevant

- `/arm/start_task`
- `/arm/stop_task`
- `/arm/stop`
- `/arm/home`
- `/arm/reset_fault`
- `/arm/activate_calibration`
- `/arm/set_mode`

### Maintenance / calibration support

- `/calibration_manager_node/reload`

## 4. Actions

### Canonical / compatibility-relevant actions

- `/arm/pick_place_task`
- `/arm/homing`
- `/arm/recover`

### Non-public / constrained actions

- `/arm/manual_servo`
- `/arm/home_sequence`

这些 action 在 generated runtime contract 中已经被标成 `experimental` 或不属于 public operator surface；文档不应把它们写成默认公开主链。

## 5. Internal topics

下面这些 topic 存在，但属于 internal/runtime-input surface，不应当作公开接口宣传：

- `/arm/internal/execution_status`
- `/arm/internal/hardware_cmd`
- `/arm/internal/ros2_control_cmd`
- `/arm/internal/stop_cmd`

同理，`INTERNAL_PLAN_TO_POSE`、`INTERNAL_PLAN_TO_JOINTS` 这类 runtime interface 也不应被包装成 public API。

## 6. Ownership 视角

按 generated runtime contract 的 package ownership，高层可分为：

- planning：`arm_motion_planner`
- execution：`arm_motion_executor`
- hardware io：`arm_hardware_bridge`
- readiness：`arm_readiness_manager`
- safety：`arm_safety_supervisor`
- lifecycle supervision：`arm_lifecycle_manager`
- task orchestration：`arm_task_orchestrator`
- perception input：`arm_camera_driver`
- perception processing：`arm_perception`

## 7. 修改规则

新增或修改 ROS2 interface 时，应同步：

1. 更新 interface 定义与 owner
2. 更新 generated runtime contract
3. 更新本索引
4. 若影响 gateway/front，对应更新 API contract 与消费层
