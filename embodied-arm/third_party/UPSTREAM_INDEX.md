# Third-Party Upstream Index

当前归档不含任何 vendored upstream source。

## Reserved integration slots

- `third_party/moveit2/`
- `third_party/ur_ros2_driver/`
- `third_party/ros2_control_demos/`
- `third_party/BehaviorTree.CPP/`

只有当以下四项同时满足时才允许新增真实源码：

1. `THIRD_PARTY_NOTICES.md` 已更新；
2. 对应目录带 `UPSTREAM.md`；
3. release manifest 已记录 provenance；
4. 验证脚本已覆盖新增 upstream。
