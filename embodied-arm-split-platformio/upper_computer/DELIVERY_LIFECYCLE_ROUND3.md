# Delivery Round 3 — Managed Lifecycle Rollout

## Scope
- official runtime-core lifecycle rollout
- managed lifecycle bringup manager
- lifecycle-aware launch registration
- camera/perception runtime node adapters
- lifecycle guard rails for active/inactive transitions

## Important constraint
This container does not include a live ROS 2 runtime (`rclpy`, `lifecycle_msgs`, `ros2`, `colcon`). Validation here is static/source-level and repository-test based, not a full Humble bringup session.
