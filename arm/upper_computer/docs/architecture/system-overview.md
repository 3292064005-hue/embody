# System Overview

> Audience: frontend, gateway, backend, firmware, release
> Owner: architecture / runtime governance
> Status: canonical
> Source of Truth: `runtime_authority.yaml`, gateway runtime projection, generated runtime contracts
> Last Update Rule: system boundary, runtime surface, or package support changes must update this document together.

> 统一术语引用：本文涉及的 runtime lane、product line、public runtime tier、runtimeSurfaceState、command plane、runtime interface、capability descriptor 统一定义见 [`terms-and-reference-blocks.md` §2-§3](terms-and-reference-blocks.md#2-运行时治理术语块)。

## 1. 本文负责什么 / 不负责什么

### 本文负责

- 说明项目边界与三大子工程职责
- 给出主链路总览与默认公开表面
- 告诉读者“哪个主题应该去看哪份 canonical 文档”

### 本文不负责

- 不逐条定义 runtime lane 与 promotion marker
- 不逐字段定义 readiness / command policy
- 不定义 REST / WebSocket payload 细节
- 不记录验证结果或签收材料

## 2. 项目目标与边界

本项目是一个 split-delivery 机械臂系统，当前仓库显式拆成三部分：

- `upper_computer/`：前端 HMI、Gateway、ROS2 backend、验证脚本、系统级文档
- `esp32s3_platformio/`：ESP32-S3 板级固件，负责 board health、reserved stream endpoint、voice/observability 扩展语义
- `stm32f103c8_platformio/`：STM32F103C8 固件，负责串口协议、ACK/NACK、状态与故障上报

当前正式交付面强调：

- **validated_sim** 是已验证的 authoritative simulation 主线
- **validated_live** 仍保留 promotion gate，默认不对外公开

本仓库的目标不是在文档层“模拟一个什么都支持的系统”，而是明确区分：

- 当前默认公开支持什么
- 哪些能力只是 experimental / compatibility / observability
- 哪些链路已经闭环，哪些必须 fail-closed

## 3. 系统分层

| 层级 | 负责什么 | 不负责什么 |
|---|---|---|
| Frontend | 操作面与观测面展示、runtimeSurfaceState、receipt/log/diagnostics 呈现 | 重新定义 authoritative truth |
| Gateway | REST/WS、runtime projection、role/policy/runtime interface gate、receipt/audit/log | 取代 backend 执行主链 |
| Backend（ROS2） | orchestration / planning / execution / dispatcher / bridge / readiness authority | 直接承担前端 UI 语义投影 |
| ESP32 固件 | board health、metadata bridge、voice/observability 扩展语义 | 独立 authoritative 执行主链 |
| STM32 固件 | 串口命令执行、ACK/NACK、状态 / 故障上报 | 系统级产品面治理 |

## 4. 主链路总览

当前 canonical task 主链是：

`task template -> gateway startTask gate -> backend orchestration -> planning -> execution -> dispatcher -> hardware bridge -> state/readiness feedback -> gateway projection -> frontend`

这条链的关键约束：

1. task start 进入 public API 前必须先通过 command policy 与 runtime interface gate
2. transport dispatch、failure mapping、receipt / audit / log 必须走统一执行管线
3. task lane 只有在 promotion 与 runtime gate 满足时才允许公开为更高 tier；否则 fail-closed

## 5. 控制平面与观测平面

系统公开面只区分两类：

- **public command planes**：驱动执行或系统状态变化
- **observability planes**：只提供观测/事件，不得被包装成 authoritative execution surface

具体术语和治理边界不在本文件重复展开，统一见 [`terms-and-reference-blocks.md` §3](terms-and-reference-blocks.md#3-命令与治理术语块)、[`runtime-governance.md`](runtime-governance.md) 与 [`command-lifecycle-and-state-ownership.md`](command-lifecycle-and-state-ownership.md)。

## 6. 默认公开表面

本文件只给高层结论：

- `preview`：用于 contract 验证、链路联调、只读工作台
- `validated_sim`：当前公开的 authoritative simulation 主线
- `validated_live`：默认不公开，需 promotion 后才能提升公开语义

具体 lane、product line、promotion、public tier 的定义统一见 [`runtime-governance.md`](runtime-governance.md) 与 [`terms-and-reference-blocks.md` §2](terms-and-reference-blocks.md#2-运行时治理术语块)。

## 7. 当前包支持快照

| package | class | active-lane included | note |
|---|---|---|---|
| `arm_esp32_gateway` | runtime-core | yes | runtime core representative package, shipped in active delivery tree |
| `arm_hmi` | experimental | no | archived / non-delivery representative package |

- Runtime Core representative packages: `arm_esp32_gateway`, `arm_readiness_manager`, `arm_motion_planner`, `arm_motion_executor`, `arm_task_orchestrator`
- Experimental representative packages: `arm_hmi`

## 8. 文档与代码的对应关系

| 你要查什么 | 先看哪份文档 |
|---|---|
| runtime lane / promotion / public tier | `runtime-governance.md` |
| readiness / command gate / runtime interface | `readiness-and-safety.md` |
| 命令 accepted/completed 语义、状态 ownership | `command-lifecycle-and-state-ownership.md` |
| authority concern 拆分与 projection | `runtime-authority-section-projections.md` |
| public REST / WebSocket payload | `../interfaces/api-contract.md` |
| ROS2 topics/services/actions | `../interfaces/ros2-interface-index.md` |
| 固件集成与联调顺序 | `../operations/firmware-integration.md` |
| 验证与发布要求 | `../operations/verification-and-release.md` |

## 9. 修改本文件时的同步项

修改以下内容时，至少同步检查：

- 系统边界或层级职责：`README.md`、`upper_computer/README.md`
- 默认公开表面：`runtime-governance.md`、generated runtime summary
- 主链路描述：`api-contract.md`、gateway tests、相关 README
