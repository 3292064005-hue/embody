# REST API Contract

All successful responses use a common envelope:

```json
{
  "code": 0,
  "message": "ok",
  "requestId": "req-...",
  "correlationId": "corr-...",
  "timestamp": "2026-03-31T12:00:00Z",
  "data": {}
}
```

Error responses use a stable envelope:

```json
{
  "code": 503,
  "error": "internal_error",
  "failureClass": "dependency_unavailable",
  "message": "ROS2 service unavailable: /arm/home",
  "requestId": "req-...",
  "timestamp": "2026-03-31T12:00:00Z",
  "detail": "ROS2 service unavailable: /arm/home",
  "operatorActionable": false
}
```

## Readiness semantics

- Gateway default startup state is **fail-closed bootstrap** until it receives an authoritative backend readiness snapshot.
- Explicit local HMI development may run with:
  - `EMBODIED_ARM_RUNTIME_PROFILE=dev-hmi-mock`
  - `EMBODIED_ARM_ALLOW_SIMULATION_FALLBACK=true`
- In that profile, readiness mode is `simulated_local_only` and response payloads include `simulated: true` and `authoritative: false` where applicable.
- Frontend offline fixture replay is only enabled with `VITE_ENABLE_MOCK=true` and `VITE_API_MOCK_MODE=fixture`; otherwise frontend mock mode is expected to talk to the gateway simulation profile.
- Command-policy decisions (`commandPolicies`) are sourced from the readiness snapshot carried by the runtime or by the explicit dev simulation profile. The gateway must not speculate that the target runtime is ready.

## Readiness fields

Readiness responses expose layered semantics. The generated source-of-truth artifact is `docs/generated/runtime_contract_manifest.json` and `docs/generated/runtime_contract_summary.md`.


- `runtimeHealthy`
- `modeReady`
- `allReady` (compatibility alias for `modeReady`)
- `runtimeRequiredChecks`
- `runtimeMissingChecks`
- `requiredChecks`
- `missingChecks`
- `missingDetails`
- `commandPolicies`
- `commandSummary`
- `authoritative`
- `simulated`
- `source`
- `runtimeTier` (`preview | validated_sim | validated_live`)
- `productLine` (compatibility alias of runtime tier / HMI product line)

## Hardware authority fields

Hardware summaries now distinguish connectivity from authority:

- `sourceStm32Online`
- `sourceStm32Authoritative`
- `sourceStm32TransportMode`
- `sourceStm32Controllable`
- `sourceStm32Simulated`
- `sourceStm32SimulatedFallback`

`sourceStm32Online=true` does not, by itself, imply that the runtime is connected to authoritative hardware.

## Semantic fields

System/readiness/runtime summary payloads expose:

- `controllerMode`: stable control mode for command gating
- `runtimePhase`: execution phase from the runtime pipeline
- `taskStage`: UI-facing task stage

Legacy aliases remain during the compatibility window:

- `mode` -> `runtimePhase`
- `operatorMode` -> `controllerMode`
- `currentStage` -> `taskStage`

## System
- `GET /health/live`
- `GET /health/ready`
- `GET /health/deps`
- `GET /api/system/summary`
- `GET /api/system/readiness`
- `POST /api/system/home`
- `POST /api/system/reset-fault`
- `POST /api/system/recover`
- `POST /api/system/emergency-stop`

## Task
- `GET /api/task/current`
- `GET /api/task/history`
- `GET /api/task/templates`
- `POST /api/task/start`
- `POST /api/task/stop`

### Task template source-of-truth

`GET /api/task/templates` no longer serves gateway-local hardcoded templates. The payload is projected from the generated runtime contract artifact (`docs/generated/runtime_contract_manifest.json`), which is generated from the authoritative backend file `backend/embodied_arm_ws/src/arm_bringup/config/task_capability_manifest.yaml`.

Each task template item may include:

- `id`
- `taskType`
- `label`
- `description`
- `defaultTargetCategory`
- `allowedTargetCategories`
- `resolvedPlaceProfiles`
- `requiredRuntimeTier`
- `riskLevel`
- `operatorHint`

### POST /api/task/start

Request body supports the new authoritative template path while remaining backward compatible with `taskType + targetCategory`:

```json
{
  "templateId": "pick-red",
  "taskType": "pick_place",
  "targetCategory": "red"
}
```

Successful response data includes:

- `taskId`
- `taskRunId`
- `templateId`
- `runtimeTier`
- `productLine`

The gateway resolves `taskType / targetCategory / place_profile` from the template catalog and rejects mismatched template/category combinations with `422 contract_violation`.

### Task history

`GET /api/task/history` is now projected from the durable `task_runs` ledger instead of an in-memory-only list. Finalized entries may include:

- `taskId`
- `taskRunId`
- `templateId`
- `placeProfile`
- `runtimeTier`
- `requestId`
- `correlationId`
- `durationMs`

## Hardware
- `GET /api/hardware/state`
- `POST /api/hardware/set-mode`
- `POST /api/hardware/jog-joint`
- `POST /api/hardware/servo-cartesian`
- `POST /api/hardware/gripper`

## Vision
- `GET /api/vision/targets`
- `GET /api/vision/frame`
- `POST /api/vision/clear-targets`

### Vision frame truth layers

`GET /api/vision/frame` distinguishes render availability from ingress truth. Frame payloads may include:

- `providerKind`
- `providerLabel`
- `frameIngressMode`
- `frameIngressLive`
- `cameraLive`
- `syntheticPreview`
- `frameTransportHealthy`
- `authoritativeVisualSource`
- `targetCount`

A rendered preview (`available=true`) does **not** by itself imply a live camera transport. Synthetic previews and topic/stream-backed live ingress are reported separately.

## Calibration
- `GET /api/calibration/profile`
- `GET /api/calibration/versions`
- `GET /api/calibration/profiles`
- `PUT /api/calibration/profile`
- `PUT /api/calibration/profiles/{profile_id}/activate`
- `POST /api/calibration/reload`
- `POST /api/calibration/activate`

## Logs and diagnostics
- `GET /api/logs/events`
- `GET /api/logs/audit`
- `GET /api/diagnostics/summary`

Diagnostics summary includes `observability` metrics:

- `queueDepth`
- `droppedRecords`
- `strictSync`
- `lastFlushAt`
- `lastFlushDurationMs`
- `lastFsyncDurationMs`
- `lastError`

Persistent streams include audit/log sinks and the durable `task_runs.jsonl` ledger used to reconstruct task history.

## Roles
- `viewer`: read-only
- `operator`: task control, home, reset
- `maintainer`: calibration, jog, servo, target clearing, maintenance actions

## Error rules
- `403`: role or authorization failure (`failureClass=operator_blocked`)
- `409`: readiness or command precondition failure (`failureClass=readiness_blocked`)
- `422`: request body validation failure (`failureClass=contract_violation`)
- `503`: runtime / dependency unavailable (`failureClass=dependency_unavailable`)
- `504`: transient command timeout (`failureClass=transient_io_failure`)

`operatorActionable=false` is reserved for failures the operator cannot fix directly from the HMI, such as backend transport outages or timeouts.

## Bringup / lifecycle visibility

- Compatibility topic: `/arm/bringup/status`
- Typed shadow topic: `/arm/bringup/status_typed`
- Both carry the same canonical JSON payload semantics via the typed message `raw_json` field during migration.
