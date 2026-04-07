# API Contract v3

## REST

### GET /api/system/summary
返回系统总状态。

### POST /api/system/home
执行受控回零。

### POST /api/system/reset-fault
复位故障状态。

### POST /api/system/emergency-stop
触发急停并进入安全停车态。

### GET /api/task/current
返回当前任务，空任务返回 `null`。

### GET /api/task/templates
返回任务模板列表。

### GET /api/task/history
返回任务历史。

### POST /api/task/start
```json
{
  "taskType": "pick_place",
  "targetCategory": "red",
  "templateId": "pick-red"
}
```

### POST /api/task/stop
停止当前任务。

### GET /api/vision/targets
获取当前识别目标列表。

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
4. 日志与诊断应支持按 `taskId / requestId / correlationId` 追踪。
