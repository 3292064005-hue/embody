# API Contract v3

## REST

### GET /api/system/summary
返回系统总状态。

### POST /api/system/home
执行受控回零。返回 transport result payload，而不是空 body。`data` 至少包含：
- `success`
- `message`
- `localPreviewOnly`
- `commandMode`

当 `localPreviewOnly=true` 时，表示本次命令只投影到显式本地 preview 状态，没有下发到权威 ROS runtime。

### POST /api/system/reset-fault
复位故障状态。返回与 `/api/system/home` 相同的 transport result payload。

### POST /api/system/emergency-stop
触发急停并进入安全停车态。返回与 `/api/system/home` 相同的 transport result payload。

### GET /api/task/current
返回当前任务，空任务返回 `null`。

### GET /api/task/templates
返回任务模板列表。模板不再来自网关本地硬编码，而是来自后端权威 `task_capability_manifest.yaml` 生成后的运行时契约产物。每个模板可包含 `allowedTargetCategories / resolvedPlaceProfiles / requiredRuntimeTier / operatorHint`。

### GET /api/task/history
返回任务历史。该接口现在来自 durable `task_runs` 账本投影，历史项可包含 `taskRunId / templateId / placeProfile / runtimeTier / requestId / correlationId / durationMs`。

### POST /api/task/start
```json
{
  "templateId": "pick-red",
  "taskType": "pick_place",
  "targetCategory": "red"
}
```

推荐以前端模板驱动的 `templateId` 作为主入口；`taskType + targetCategory` 仅保留兼容路径。成功返回会带上 `taskId / taskRunId / templateId / runtimeTier / productLine`；其中 `runtimeTier / productLine` 表示当前实际 runtime 车道，而不是模板最低门槛。

### POST /api/task/stop
停止当前任务。返回 transport result payload，而不是空 body。`data` 至少包含：
- `success`
- `message`
- `localPreviewOnly`
- `commandMode`

这使“本地 preview 停止任务”与“权威运行时已实际停止任务”在接口语义上明确区分。

### GET /api/vision/targets
获取当前识别目标列表。

### GET /api/vision/frame
获取当前帧摘要。返回值会区分渲染可用性与视觉真值来源，可能包含：
- `providerKind / providerLabel`
- `frameIngressMode / frameIngressLive`
- `cameraLive / syntheticPreview`
- `frameTransportHealthy`
- `authoritativeVisualSource / targetCount`

这意味着页面能显示预览，不等于真实摄像头 transport 已在线。

### GET /api/calibration/profile
获取当前激活的标定参数。

### GET /api/calibration/profiles
获取标定 profile 版本列表。

### PUT /api/calibration/profile
更新当前标定参数。

### PUT /api/calibration/profiles/:id/activate
激活指定 profile。

### GET /api/hardware/state
获取硬件状态快照。

### POST /api/hardware/gripper
```json
{
  "open": true
}
```

返回 transport result payload，字段与 system/task command 一致：`success/message/localPreviewOnly/commandMode`。

### POST /api/hardware/jog-joint
```json
{
  "jointIndex": 0,
  "direction": 1,
  "stepDeg": 2
}
```

### GET /api/logs
获取结构化日志列表。

## 通用 REST 响应

```json
{
  "code": 0,
  "message": "ok",
  "requestId": "req-xxxx",
  "timestamp": "2026-03-31T10:00:00.000Z",
  "data": {}
}
```

## Command transport result

下列命令型接口统一返回 transport result payload，而不是空 body：
- `/api/system/home`
- `/api/system/reset-fault`
- `/api/system/emergency-stop`
- `/api/system/recover`
- `/api/task/stop`
- `/api/hardware/gripper`
- `/api/hardware/jog-joint`
- `/api/hardware/servo-cartesian`
- `/api/hardware/set-mode`

字段约定：
- `success`: transport 是否被接受
- `message`: 网关/bridge 返回的结果说明
- `localPreviewOnly`: 是否仅做本地 preview 投影
- `commandMode`: `authoritative_transport` / `local_preview_only` / `fixture_mock`

前端不得把 `localPreviewOnly=true` 的结果渲染成“硬件已执行”或“运行时已执行”。

## WebSocket Envelope

```json
{
  "event": "system.state.updated",
  "timestamp": "2026-03-31T10:00:00.000Z",
  "source": "gateway",
  "requestId": "req-xxxx",
  "taskId": "task-xxxx",
  "correlationId": "corr-xxxx",
  "seq": 12,
  "schemaVersion": "1.0",
  "data": {}
}
```

## 典型事件

- `system.state.updated`
- `vision.targets.updated`
- `task.progress.updated`
- `hardware.state.updated`
- `log.event.created`
- `server.pong`

## 前端运行时规则

1. 危险命令必须先过前端安全门禁，再由后端网关二次校验。
2. 关键同步失败后，前端可进入 `readonlyDegraded` 只读降级态。
3. 所有命令型操作都必须生成审计记录。
4. 日志与诊断应支持按 `taskId / taskRunId / requestId / correlationId` 追踪。
5. 前端必须按 `runtimeTier/productLine` 和任务模板能力渲染控制面，不得自行脑补模板或视觉 live 状态。
