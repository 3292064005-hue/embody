# Readiness Rules

> Generated sync artifact: `docs/generated/runtime_contract_manifest.json` records the exact public readiness fields, command names, and mode/check matrix exported from code.


Readiness is **layered**, **mode-aware**, and **time-sensitive**.

## Layered semantics

Gateway / HMI must not collapse all readiness into one boolean.

### 1. `runtimeHealthy`
Runtime-wide prerequisites that must be healthy before the system can be treated as an authoritative runtime:

- `ros2`
- `task_orchestrator`
- `motion_planner`
- `motion_executor`
- `hardware_bridge`
- `calibration`
- `profiles`

`runtimeHealthy=false` means the runtime is alive enough to report status, but not healthy enough to be presented as a fully authoritative control runtime.

### 2. `modeReady`
Mode-specific readiness derived from the active controller mode.

Required checks by mode:

- `idle`: `ros2`, `task_orchestrator`, `hardware_bridge`, `calibration`, `profiles`
- `task`: `ros2`, `task_orchestrator`, `motion_planner`, `motion_executor`, `hardware_bridge`, `camera_alive`, `perception_alive`, `target_available`, `calibration`, `profiles`
- `manual`: `ros2`, `task_orchestrator`, `hardware_bridge`
- `maintenance`: `ros2`, `task_orchestrator`, `hardware_bridge`
- `safe_stop`: `ros2`, `hardware_bridge`
- `fault`: `ros2`, `hardware_bridge`

### 3. `commandPolicies`
Per-command gate decisions surfaced to the UI and REST layer.

`modeReady=true` does **not** mean every command is permitted. The final command gate is always the per-command policy.

## Command policy rules

公开命令当前至少包含：

- `startTask`
- `stopTask`
- `jog`
- `servoCartesian`
- `gripper`
- `home`
- `resetFault`
- `recover`

其中：

- `startTask` 仍依赖 task-ready / planning-authoritative 语义；
- `jog / servoCartesian / gripper / recover` 在 `manual/maintenance` 下按命令粒度放行，不再因为 `motion_planner` 非 authoritative 被整组拖死；
- `home / resetFault` 仍必须尊重硬件 authority 与故障态语义。

## Vision-chain rules

The official runtime now distinguishes between:

- camera frame freshness
- camera health summary
- perception activity
- authoritative primary target
- compatibility multi-target summary

Authoritative readiness decisions use the **primary target contract** on `/arm/vision/target`.
Compatibility consumers may still observe `/arm/vision/targets`, but that topic is not the source of truth for readiness.

### Vision-related checks

- `camera_alive`: recent valid camera activity, not merely process liveness
- `perception_alive`: recent perception processing activity, not merely cached targets
- `target_available`: recent authoritative target publication

## Hardware authority rules

`hardware_bridge` is ready only when the STM32 transport is:

- online
- fresh
- not faulted
- `transportMode=real`
- `authoritative=true`

Simulated transport is allowed only in explicit development profiles and must be surfaced as non-authoritative.

## Staleness

Each check expires if not refreshed within its allowed interval. A stale check must be treated as not ready.

For gateway-projected authoritative readiness snapshots this fail-closed rule applies to both:

- command admission
- public readiness projection (`runtimeHealthy`, `modeReady`, `allReady`, `commandPolicies`)

This applies in particular to:

- camera frame freshness
- perception freshness
- target freshness
- hardware bridge freshness

## Derived fields

Readiness payloads must expose:

- `runtimeHealthy`
- `modeReady`
- `allReady` (compatibility alias of `modeReady`)
- `runtimeRequiredChecks`
- `runtimeMissingChecks`
- `requiredChecks`
- `missingChecks`
- `missingDetails`
- `commandPolicies`
- `commandSummary`
- `authoritative`
- `simulated`

## UI rules

Top-level UI must separately show:

- runtime health
- mode readiness
- command readiness summary
- hardware authority / simulation status

The UI must not render a single generic `READY` badge that implies all commands are executable.
