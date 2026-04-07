# Test Cases v3

## Unit
- `domain/safety/guards.test.ts`
  - 健康状态允许启动任务
  - stale 阻止启动任务
  - 非工程模式阻止点动
  - demo 模式阻止夹爪控制
  - snapshot 摘要可用于审计链

## Runtime / Store
- `connectionStore`
  - 心跳 / pong / stale / readonlyDegraded
- `taskStore`
  - 任务启动后触发失效刷新
  - 门禁失败时写 blocked 审计
- `robotStore`
  - 点动 / 夹爪命令均写审计
- `visionStore`
  - 保存标定后刷新 profile 与版本列表
- `logStore`
  - level / task / request / correlation 筛选

## E2E
1. Dashboard 启动后可见“任务控制台 / 连接健康 / 控制安全状态”
2. Mock 模式下系统进入可控状态
3. 故障态时禁止新任务
4. 演示模式禁止夹爪直控
5. 工程模式允许点动
6. 标定 profile 可切换激活
7. 日志可按 requestId / correlationId 过滤
8. 急停后界面进入安全停车 / 只读提示链
