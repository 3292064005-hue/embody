# Deep Review Report

本轮对照基准：
- `基于 ROS2 的桌面具身智能机械臂抓取与交互系统项目规划书`
- `逐包改造设计说明书`
- `Core SOP & Ironclad Rules`

## 已修正的真实缺陷

1. **Action 路径语义错误**
   - 现象：Gateway 在走 `PickPlaceTask` action 时把 `task_type` 填进了 `target_type`，导致目标选择器丢失。
   - 修复：
     - `gateway/ros_bridge.py` 只在 `PICK_AND_PLACE` 时走 pick/place action。
     - action payload 改为用 `target_type` 承载目标选择器。
     - `task_orchestrator_node.py` 新增兼容归一化逻辑，兼容旧客户端把任务类型误塞进 `target_type` 的情况。

2. **无效 JSON 可能导致运行时回调抛异常**
   - 现象：`motion_planner_node.py`、`motion_executor_node.py` 直接 `json.loads()`，坏 payload 会在运行时抛异常。
   - 修复：统一改为安全解析，坏 payload 返回 `{}`，并通过 summary 给出 reject 状态。

3. **README / 架构文档与实际主链不一致**
   - 现象：根 README 与 backend README 仍把 `arm_vision` 写成主链组件。
   - 修复：改为 `arm_camera_driver + arm_perception`，并补入验证环境矩阵。

4. **边界输入缺少显式校验**
   - 现象：Gateway 对非法 `taskType`、非法 calibration ROI 仍可能走到业务层。
   - 修复：`gateway/schemas.py` 改为强约束 schema，非法请求直接 422。

## 新增验证

- `backend/embodied_arm_ws/tests/test_boundary_and_regression_guards.py`
- `gateway/tests/test_runtime_contracts.py` 追加 schema 边界测试
- `gateway/tests/test_server.py` 追加 action routing regression 测试

## 当前可实证结论

- 仓库级 pytest 通过
- frontend typecheck/build/unit test 通过
- `final_audit.py` 通过
- compileall 通过

## 仍需目标环境实证的部分

- ROS2 `colcon build` + launch
- MoveIt 真实联跑
- STM32 / ESP32 / Camera HIL


## 本轮追加修正（batch8）

1. **P0 / P1 可追踪性补强**
   - 新增 `docs/P0_P1_TRACEABILITY.md`，将方案里的 P0/P1 项逐一映射到实际测试。
   - 新增 `backend/embodied_arm_ws/tests/test_p0_p1_coverage.py`，补上 launch smoke、sim pick-place、cancel task、recover 行为测试。

2. **环境矩阵收敛到项目元数据**
   - 根目录新增 `.nvmrc` 与 `.python-version`。
   - `frontend/package.json` 新增 `engines`，与 README 的 Node.js / npm 矩阵对齐。
   - `gateway/README.md` 与 `frontend/README.md` 补入验证环境矩阵。

3. **Recover 入口补全**
   - Gateway 新增 `/api/system/recover`。
   - `gateway/ros_bridge.py` 新增 recover action/service 入口。
   - 新增回归测试，验证急停后 reset-fault + recover 能恢复到 idle。

4. **前端门禁测试补齐**
   - 新增 `frontend/src/stores/safety.test.ts`，对 readiness / stale realtime / homed 条件进行显式验证。

5. **发现并修复压缩包依赖一致性问题**
   - 压缩包内旧 `node_modules` 的 `vue-tsc` 二进制入口损坏，导致 `npm run typecheck` 失败。
   - 已通过 `npm ci --ignore-scripts` 重新安装依赖，并在修正后的工作树上重新完成 typecheck / build / unit test。
