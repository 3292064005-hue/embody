# Embodied Arm HMI v3

面向“基于 ROS2 的桌面具身智能机械臂抓取与交互系统”的前端 HMI 主控台。

本版本在 v2 基础上继续强化，不再只是页面骨架，而是把前端提升为：

- **控制面**：任务启动 / 停止 / 回零 / 急停 / 故障复位 / 维护点动 / 笛卡尔微调
- **观测面**：状态机、连接健康、日志诊断、历史任务、视觉目标与标定版本
- **同步面**：统一 REST 拉取、失效刷新、只读降级、审计链与 Mock 运行时

## 技术栈

- Vue 3
- TypeScript
- Vite
- Pinia
- Vue Router
- Element Plus（显式注册）
- Axios
- Vitest
- Playwright

## 本轮升级重点

### 1. 实时与同步
- `useHmiRealtime`：统一接入 WebSocket / Mock 心跳
- `useServerStateSync`：统一拉取系统、任务、视觉、硬件、日志等服务端状态
- `shared/runtime/invalidation.ts`：命令成功后精确失效刷新
- `connectionStore`：链路质量、stale、解析错误、同步错误、只读降级

### 2. 安全与审计
- `domain/safety/guards.ts`：纯函数门禁规则
- `safetyStore`：统一导出“能不能启动 / 点动 / 夹爪 / 回零 / 复位”
- `auditStore`：危险命令审计记录，支持 pending / success / failed / blocked
- `X-Operator-Role` 与 Gateway 的 `viewer / operator / maintainer` 模型对齐

### 3. Mock / Simulation 运行时
- `shared/mock/runtime.ts`：前端 fixture / replay 数据层，不再作为权威业务状态机
- `services/api/mockAdapter.ts`：仅在 `VITE_API_MOCK_MODE=fixture` 时启用的离线 fixture adapter
- 默认本地联调以 Gateway `dev-hmi-mock` simulation 为权威真源；设置 `VITE_ENABLE_MOCK=true` 且 `VITE_API_MOCK_MODE=gateway` 时，前端仍连 Gateway，而不是旁路成前端本地状态机
- 仅 UI 脱机演示 / Playwright 预览使用 `VITE_API_MOCK_MODE=fixture`

### 4. 页面升级
- Dashboard：链路质量、只读降级、成功率与事件流
- Task Center：模板选择、当前阶段、历史任务
- Vision：标定 profile 版本、误差比较、激活切换
- Maintenance：工程模式门禁、点动限幅、笛卡尔微调、命令审计
- Logs：level / task / request / correlation / 诊断摘要过滤与详情侧栏
- Settings：过期阈值、只读降级策略、自动刷新等

## 运行

```bash
npm ci
npm run dev
```

## 构建与检查

```bash
npm run typecheck
npm run build
npm run test:unit
npm run test:e2e
```

## 环境变量

见 `.env.example`。

默认接口：

- REST: `/api/*`
- WebSocket: `/ws`

## 目录结构

```bash
src/
├── components/
├── composables/
├── domain/
├── layouts/
├── models/
├── pages/
├── services/
├── shared/
├── stores/
└── utils/
```

## 说明

- 控制命令不直接碰 ROS2 底层，而是统一通过 HMI Gateway。
- Gateway mock 模式是联调真源；fixture mock 仅提供离线回放与轻量本地覆盖，不承担权威业务状态推进。
- 本版本已经把“页面能跑”升级到“链路可诊断、控制可审计、状态可回放”的 HMI 形态。


## Validated environment matrix

- OS: **Ubuntu 22.04 LTS**
- Node.js: **22.x**
- npm: **10.9.2**
- Vue: **3.5.x**
- Vite: **6.x**
