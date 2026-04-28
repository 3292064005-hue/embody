# Gateway

FastAPI BFF，负责：

- REST / WebSocket
- runtime projection
- command policy / runtime interface gate
- receipt / audit / log

## 1. 先看

- [../docs/INDEX.md](../docs/INDEX.md)
- [../docs/interfaces/api-contract.md](../docs/interfaces/api-contract.md)
- [../docs/architecture/readiness-and-safety.md](../docs/architecture/readiness-and-safety.md)
- [../docs/architecture/runtime-governance.md](../docs/architecture/runtime-governance.md)

## 2. Gateway 在系统中的职责

Gateway 是 public contract 的统一出口。它负责：

- 把 backend / firmware / runtime authority 投影为 operator-facing REST 与 WebSocket
- 执行 command plane、role、mode、runtime interface gate
- 统一生成 receipt / audit / log
- 对外输出 `runtimeSurfaceState` 等公共语义面

Gateway 不应成为另一个“事实定义源”。它必须消费：

- generated runtime contracts
- runtime authority 派生产物
- OpenAPI / generated client 同步结果

## 3. Environment contract

- OS: **Ubuntu 22.04 LTS**
- Python: **3.10.x**
- ROS 2: **Humble**
- Node.js: **22.x**
- npm: **10.9.2**

## 4. 启动

```bash
pip install -r requirements.txt -c constraints.txt
python -m gateway.main
```

## 5. 当前执行与投影原则

- public command plane 统一经 `runtime_command_gateway`
- readiness public surface 以 `runtimeSurfaceState` 为主
- task/manual/system 命令需要经过 role、policy、runtime interface 三层 gate
- blocked / failed / accepted / success / observability 都应进入 receipt ledger


## 5.1 Observability sink

运行期观测日志目录由 `EMBODIED_ARM_OBSERVABILITY_DIR` 控制。该目录属于 transient/runtime state，不进入 release package。

## 6. 文档边界

Gateway README 不再重复定义完整 API、runtime lane 或 release gate 事实。详细字段、路由 contract、runtime truth 和 promotion 规则统一以 canonical 文档和 generated contracts 为准。
