# Terms and Reference Blocks

> Audience: all canonical-document authors, reviewers, and maintainers
> Owner: project documentation / runtime governance
> Status: canonical
> Source of Truth: runtime authority, generated runtime contracts, gateway projection, verification scripts
> Last Update Rule: when a term here changes, update every canonical document that references this file in the same change.

本文件提供 **canonical 文档之间共享的术语与引用块**。目的不是再造一份“大而全总说明”，而是把高频重复概念收敛到一个统一位置，然后让其它权威文档只保留：

- 本文特有的规则
- 本文特有的边界
- 指向本文件的引用

使用原则：

1. 涉及 runtime lane / product line / runtime tier / runtime surface 时，优先引用 [§2 运行时治理术语块](#2-运行时治理术语块)。
2. 涉及 command plane / runtime interface / capability descriptor / receipt 闭环时，优先引用 [§3 命令与治理术语块](#3-命令与治理术语块)。
3. 涉及 repository validation lane / target runtime lane / HIL / 结果表述时，优先引用 [§4 验证与发布术语块](#4-验证与发布术语块)。
4. 涉及 canonical / generated / evidence / archive 文档生命周期时，优先引用 [§5 文档生命周期术语块](#5-文档生命周期术语块)。

## 1. 如何在其它文档中引用

建议使用如下形式，而不是在每份文档里重写同样的概念：

> 本文涉及的 runtime lane、product line、public runtime tier、runtimeSurfaceState 统一定义见 [`terms-and-reference-blocks.md` §2](terms-and-reference-blocks.md#2-运行时治理术语块)。

> 本文涉及的 command plane、runtime interface、capability descriptor、receipt 闭环统一定义见 [`terms-and-reference-blocks.md` §3](terms-and-reference-blocks.md#3-命令与治理术语块)。

## 1.1 推荐写法与禁用写法

| 场景 | 推荐写法 | 避免写法 |
|---|---|---|
| 描述当前正式公开运行面 | “当前默认公开的 authoritative 主线是 validated_sim。” | “系统已经支持 validated_live。” |
| 描述 generated 文档 | “只读生成物，以事实源与生成脚本为准。” | “这里可以手工修一下。” |
| 描述 observability ingress | “受 runtime interface gate 管理的 observability ingress。” | “只是观测，不需要治理。” |
| 描述 readiness | “分层 readiness 投影。” | “一个 allReady 就够了。” |
| 描述验证结果 | “已静态确认 / 已沙箱验证 / 未真实环境验证。” | “已经完全可交付。” |

## 2. 运行时治理术语块

### 2.1 Runtime lane

`runtime lane` 是底层运行配置与执行骨架的命名面，决定系统当前以哪类环境、哪类背板、哪类依赖组合运行。它不是 operator-facing 的最终公开结论。

### 2.2 Product line

`product line` 是对外可交付能力的治理分层，用于表达某类 lane 对外是否属于正式、可交互、可公开支持的产品表面。

### 2.3 Public runtime tier

`public runtime tier` 是 operator-facing 的最终公开级别。它由 lane、promotion、public exposure、fail-closed 规则共同决定；不能仅根据 launch 名称或内部 lane 名称推断。

### 2.4 Runtime surface state

`runtimeSurfaceState` 是前端和 operator-facing API 应优先消费的统一公开语义面。它是投影层，不是新的事实源；事实源仍然是 runtime authority 和生成合同。

### 2.5 Preview / validated_sim / validated_live

- `preview`：面向 contract 验证、联调、只读工作台，必须 fail-closed。
- `validated_sim`：当前正式公开的 authoritative simulation 主线。
- `validated_live`：默认不对外公开；只有 promotion 证据齐备后，才允许被投影为正式 live 公开表面。

## 3. 命令与治理术语块

### 3.1 Command plane

`command plane` 是 operator-facing 的执行或系统控制入口分类。它定义命令属于哪类公共治理平面，例如 `task_control`、`manual_control`、`system_control`。

### 3.2 Runtime interface

`runtime interface` 是 command plane 或内部入口的运行时注册表。它描述某入口当前是否 `active`、`experimental` 或 `reserved`，并作为执行前门控的一部分。

### 3.3 Capability descriptor

`capability descriptor` 是 operator-facing 的能力描述层。它补充说明 data plane、control plane、execution binding、authority level，但不替代 command plane 或 runtime interface gate。

### 3.4 Receipt / audit / log 闭环

统一执行管线应保证所有 `accepted / blocked / failed / success / observed / rejected` 路径都能形成：

- receipt
- audit（适用时）
- log

任何一条 public ingress 绕开这个闭环，都属于治理缺口。

### 3.5 Observability plane

`vision_observability`、`voice_observability` 属于受治理的 runtime ingress。它们不是 execution command，但也不应绕过 runtime interface gate、receipt 与日志。

## 4. 验证与发布术语块

### 4.1 Repository validation lane

在无 ROS2 真机环境下完成的仓库级验证面，重点覆盖合同、单元测试、前端构建、审计与打包门禁。

### 4.2 Target runtime lane

对齐目标环境的运行面，通常要求 Ubuntu 22.04、ROS 2 Humble、active overlay，以及更接近真实 bringup 的运行条件。

### 4.3 HIL / release lane

面向 validated_live promotion 的高门槛验证面，需要 target runtime gate、HIL smoke、release checklist 与证据归档。

### 4.4 结果表述

允许使用：

- 已静态确认
- 已沙箱验证
- 未真实环境验证

禁止把以下表述写得强于证据：

- 静态检查通过 = 完全可交付
- validated_sim 通过 = validated_live 可交付
- 证据不齐全却写成正式 live 可用

## 5. 文档生命周期术语块

### 5.1 Canonical

长期维护、可手改、定义系统事实与流程的文档。

### 5.2 Generated

脚本生成的只读文档。发生漂移时，应修改事实源或生成脚本，而不是手工修 generated 文件。

### 5.3 Evidence

记录验证结果、签收材料、promotion 证据的文档。它们提供结果，不定义规则。

### 5.4 Archive

迁移期或历史文档，仅供追溯背景，不再作为当前系统事实源。
