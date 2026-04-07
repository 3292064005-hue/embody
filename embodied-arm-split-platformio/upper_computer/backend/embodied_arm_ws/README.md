# embodied_arm_ws

ROS2 backend workspace for the embodied robotic arm project.

## Stack layout

### Official Runtime Core

- `arm_profiles`: task and placement profile loading
- `arm_calibration`: calibration profile loading and activation
- `arm_hardware_bridge`: STM32 / ESP32 transport, dispatcher and semantic state aggregation
- `arm_readiness_manager`: backend readiness aggregation and command-policy source of truth
- `arm_safety_supervisor`: safety supervision and fault latching
- `arm_camera_driver`: camera source adapter for the runtime chain
- `arm_perception`: target stream normalization and publication
- `arm_scene_manager`: runtime planning-scene synchronization and attachment state
- `arm_grasp_planner`: runtime grasp candidate generation and selection
- `arm_motion_planner`: planning entrypoint for pick/place and manual motion requests
- `arm_motion_executor`: hardware command stream generation and validation
- `arm_task_orchestrator`: task queue, state machine, retry and verification loop
- `arm_diagnostics`, `arm_logger`: runtime summaries and logging

### Runtime supervision / compatibility / experimental packages

- Runtime supervision: `arm_lifecycle_manager`
- Compatibility only: `arm_task_manager`, `arm_motion_bridge`
- Experimental only: `arm_hmi`, `arm_esp32_gateway`

## Validated environment matrix

- OS: **Ubuntu 22.04 LTS**
- ROS 2: **Humble**
- Python: **3.10+**
- Node.js: **22.x**
- npm: **10.9.2**

## Runtime contract migration

- `arm_interfaces` is the sole authoritative interface source.
- `arm_msgs` remains a deprecated mirror for compatibility only.
- Readiness / task status / diagnostics summary / calibration profile / target array now publish typed shadow topics alongside legacy JSON compatibility topics.
- Gateway consumes typed topics first and falls back to JSON compatibility topics when typed contracts are unavailable.

## Quick start

```bash
colcon build --symlink-install
source install/setup.bash
ros2 launch arm_bringup runtime_sim.launch.py
```

### Legacy / demo launch variants

- `sim.launch.py`: compatibility simulation entrypoint
- `sim_with_mock_target.launch.py`: simulation plus mock target injection
- `hybrid.launch.py`: mixed camera/hardware path for integration debugging
- `hw.launch.py`: hardware-biased bringup
- `full_demo.launch.py`: demo entrypoint that may include optional demo assets

## Target-environment validation

For a real target-environment check on Ubuntu 22.04 + ROS 2 Humble, run:

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
pytest -q tests/test_ros_launch_smoke.py tests/test_gateway_dispatcher_feedback_roundtrip.py
```

Or from the repository root:

```bash
make target-env-check
make ros-target-validate
```


Additional lane aliases:

```bash
ros2 launch arm_bringup runtime_sim.launch.py
ros2 launch arm_bringup runtime_hybrid.launch.py
ros2 launch arm_bringup runtime_real.launch.py
```

`official_runtime.launch.py` remains a compatibility alias to the sim lane.
