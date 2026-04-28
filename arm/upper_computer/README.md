# Upper Computer

`upper_computer/` 是上位机完整工程目录，包含：

- `frontend/`：HMI
- `gateway/`：REST / WS / runtime projection / command policy / runtime interface gate
- `backend/embodied_arm_ws/`：ROS2 split-stack workspace
- `docs/`：系统级 canonical / generated / evidence / archive 文档
- `scripts/`：验证、生成、环境与发布脚本

## 1. 文档入口

请先看：

- [docs/INDEX.md](docs/INDEX.md)

### 按角色阅读

| 角色 | 建议顺序 |
|---|---|
| 新接手开发者 | `INDEX.md` → `system-overview.md` → `quick-start.md` |
| Gateway / Frontend 开发 | `runtime-governance.md` → `readiness-and-safety.md` → `interfaces/api-contract.md` |
| Backend / Bringup 开发 | `system-overview.md` → `runtime-governance.md` → `firmware-integration.md` |
| QA / Release | `verification-and-release.md` → `hil-and-promotion.md` → `evidence/` |

## 2. 目录职责

### frontend

负责：

- operator-facing HMI
- runtimeSurfaceState、command receipt、targets/frame 的前端展示
- 对 gateway canonical contract 的消费

### gateway

负责：

- public REST / WebSocket
- runtime projection
- command plane / runtime interface policy enforcement
- receipt / audit / log

### backend/embodied_arm_ws

负责：

- orchestration / planning / execution / dispatcher / bridge
- ROS2 interfaces
- runtime lane bringup

## 3. 当前运行面结论

- 默认公开：`preview` / `validated_sim`
- `validated_live`：默认不对外公开，需 promotion evidence 齐备后才可能公开

### validated_live promotion markers

- `validated_live_backbone_declared`
- `target_runtime_gate_passed`
- `hil_gate_passed`
- `release_checklist_signed`

这些 marker 既是 release / HIL 的证据要求，也是 README 层面对外陈述时不能越过的边界。任何没有这四项证据的环境，都不能把自己写成默认对外开放的 validated live。

## 4. Validated environment matrix

- OS: **Ubuntu 22.04 LTS**
- ROS 2: **Humble**
- Python: **3.10.x**
- Node.js: **22.x**
- npm: **10.9.2**


## 4.1 Validation lanes and target-runtime lanes

### Repository validation lane

本地与 CI 的仓库级验证目标是：

- OS: **Ubuntu 22.04 LTS**
- ROS 2: **optional**
- Python: **3.10.x**
- Node.js: **22.x**
- npm: **10.9.2**

常用入口：

```bash
make target-env-bootstrap
python scripts/verify_repository.py --profile fast
```

### Target runtime lane

面向真实 ROS2 / runtime target 的验证目标是：

- OS: **Ubuntu 22.04 LTS**
- ROS 2: **Humble**
- Python: **3.10.x**
- Node.js: **22.x**
- npm: **10.9.2**

常用入口：

```bash
make ros-target-validate-docker
bash scripts/ros_target_validation.sh
```

### Observability sink

Gateway 默认把观测日志写入由 `EMBODIED_ARM_OBSERVABILITY_DIR` 控制的目录。该目录属于运行期产物，发布打包时不应进入 release archive。

## 5. 常用运行与验证入口

### 运行

- Backend：`docs/operations/quick-start.md`
- Gateway：`gateway/README.md`
- Frontend：`frontend/README.md`

### 验证

```bash
make test-backend
make test-backend-active
make test-gateway
python scripts/verify_frontend_validation.py
python scripts/write_frontend_validation_status.py
python scripts/sync_doc_compatibility_mirrors.py --check
python scripts/final_audit.py
```

## 6. 变更影响图

| 你改了什么 | 至少要同步看 |
|---|---|
| runtime authority / generated contracts | `docs/architecture/runtime-governance.md`、`docs/INDEX.md`、gateway/front 消费层 |
| gateway public payload | `docs/interfaces/api-contract.md`、OpenAPI、frontend docs |
| readiness / safety | `docs/architecture/readiness-and-safety.md`、gateway tests |
| release / audit / package | `docs/operations/verification-and-release.md`、`docs/evidence/` |

## 7. 文档边界

本 README 只保留：

- 目录职责
- 环境矩阵
- validated_live promotion 边界
- 跳转入口
- 变更影响图

运行时 lane 细节、command plane 细节、readiness 字段定义、API 字段定义，都统一由 `docs/` 下的 canonical 文档维护，不在本 README 重复定义。
