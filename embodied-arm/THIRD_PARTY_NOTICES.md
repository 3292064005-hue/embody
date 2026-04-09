# Third-Party Notices

本仓当前 **未直接打包任何上游源码**，但设计、接口语义与治理清单参考了下列上游项目。
后续若在 `third_party/` 中引入实际源码，必须同步记录上游 commit、许可证、改动点、替换方式与回滚方式。

| Upstream | License | Current status | Intended scope |
| --- | --- | --- | --- |
| MoveIt2 | BSD-3-Clause | reference only | manipulation planning / execution semantics |
| Universal_Robots_ROS2_Driver | BSD-3-Clause | reference only | authoritative execution / fault / speed-scaling semantics |
| ros2_control_demos | Apache-2.0 | reference only | controller-manager / hardware-interface topology |
| BehaviorTree.CPP | MIT | reference only | task orchestration patterns |
| rmf-web | Apache-2.0 | reference only | API server / client / dashboard packaging patterns |
| micro_ros_platformio | Apache-2.0 | reference only | ESP32 topic-oriented integration ideas |
| rosbridge_suite | BSD-3-Clause | reference only | bridge comparison baseline only |
| ROSboard | BSD-3-Clause | reference only | lightweight observability comparison baseline only |

## Governance rules

1. 第三方源码只能放在 `third_party/<name>/`。
2. 每个第三方目录都必须带 `UPSTREAM.md`，记录：仓库、commit/tag、license、引入时间、修改点、回滚方式。
3. release manifest 必须列出 third-party inventory。
4. 未进入 `third_party/` 的项目一律按“reference only”处理，不得在代码中宣称已 vendored。
