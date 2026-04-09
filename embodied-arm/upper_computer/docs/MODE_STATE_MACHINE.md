# Mode and State Machine

## Semantic split

The public runtime contract now separates three concerns:

- `controllerMode`: stable control-plane mode used for permission / command gating
  - `idle`
  - `manual`
  - `task`
  - `maintenance`
- `runtimePhase`: current execution phase reported by the runtime
  - `boot`
  - `idle`
  - `perception`
  - `plan`
  - `execute`
  - `verify`
  - `safe_stop`
  - `fault`
- `taskStage`: UI-facing task progress stage
  - `created`
  - `perception`
  - `plan`
  - `execute`
  - `verify`
  - `done`
  - `failed`

## Compatibility aliases

The gateway/frontend still expose the legacy aliases during the compatibility window:

- `mode` -> alias of `runtimePhase`
- `operatorMode` -> alias of `controllerMode`
- `currentStage` -> alias of `taskStage`

## Rules

- `startTask` is legal only when readiness is satisfied for `task`
- `jogJoint` and `servoCartesian` are legal only in `manual` or `maintenance`
- `emergencyStop` forces `runtimePhase=safe_stop`, `controllerMode=maintenance`, `taskStage=failed`
- `resetFault` / `recover` return to `runtimePhase=idle`, `controllerMode=idle`
- UI command gating must evaluate `controllerMode + readiness`, not transient `runtimePhase`
