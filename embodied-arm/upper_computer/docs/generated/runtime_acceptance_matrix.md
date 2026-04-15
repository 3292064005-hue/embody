# Runtime Acceptance Matrix (Generated)

This file is generated from `runtime_authority.yaml`. Do not edit manually.

## `full_demo_authoritative`
- deliveryTrack: `official_active`
- officialRuntimeLane: `True`
- intendedProductLine: `validated_sim`
- effectivePublicRuntimeTier: `validated_sim`
- taskWorkbenchVisible: `True`
- taskExecutionInteractive: `True`
- acceptance checks:
  - public tier must be validated_sim
  - planning_capability must be validated_sim
  - hardware_execution_mode must be authoritative_simulation
  - forward_hardware_commands must remain true
  - task execution must be interactive

## `full_demo_preview`
- deliveryTrack: `official_active`
- officialRuntimeLane: `True`
- intendedProductLine: `preview`
- effectivePublicRuntimeTier: `preview`
- taskWorkbenchVisible: `False`
- taskExecutionInteractive: `False`
- acceptance checks:
  - public tier must remain preview
  - task execution must stay non-interactive
  - forward_hardware_commands must remain false

## `hw_preview`
- deliveryTrack: `official_active`
- officialRuntimeLane: `True`
- intendedProductLine: `preview`
- effectivePublicRuntimeTier: `preview`
- taskWorkbenchVisible: `False`
- taskExecutionInteractive: `False`
- acceptance checks:
  - public tier must remain preview
  - task execution must stay non-interactive
  - forward_hardware_commands must remain false

## `hybrid_preview`
- deliveryTrack: `official_active`
- officialRuntimeLane: `True`
- intendedProductLine: `preview`
- effectivePublicRuntimeTier: `preview`
- taskWorkbenchVisible: `False`
- taskExecutionInteractive: `False`
- acceptance checks:
  - public tier must remain preview
  - task execution must stay non-interactive
  - forward_hardware_commands must remain false

## `live_control`
- deliveryTrack: `experimental`
- officialRuntimeLane: `False`
- intendedProductLine: `preview`
- effectivePublicRuntimeTier: `preview`
- taskWorkbenchVisible: `False`
- taskExecutionInteractive: `False`
- acceptance checks:
  - delivery track must remain experimental
  - planning_capability must remain validated_live or live-candidate scoped
  - hardware_execution_mode must remain ros2_control_live or candidate live equivalent
  - public tier must fail closed to preview until promotion is effective
- required evidence:
  - `validated_live_backbone_declared`
  - `target_runtime_gate_passed`
  - `hil_gate_passed`
  - `release_checklist_signed`

## `live_proto`
- deliveryTrack: `experimental`
- officialRuntimeLane: `False`
- intendedProductLine: `preview`
- effectivePublicRuntimeTier: `preview`
- taskWorkbenchVisible: `False`
- taskExecutionInteractive: `False`
- acceptance checks:
  - delivery track must remain experimental
  - planning_capability must remain validated_live or live-candidate scoped
  - hardware_execution_mode must remain ros2_control_live or candidate live equivalent
  - public tier must fail closed to preview until promotion is effective
- required evidence:
  - `validated_live_backbone_declared`
  - `target_runtime_gate_passed`
  - `hil_gate_passed`
  - `release_checklist_signed`

## `real_preview`
- deliveryTrack: `official_active`
- officialRuntimeLane: `True`
- intendedProductLine: `preview`
- effectivePublicRuntimeTier: `preview`
- taskWorkbenchVisible: `False`
- taskExecutionInteractive: `False`
- acceptance checks:
  - public tier must remain preview
  - task execution must stay non-interactive
  - forward_hardware_commands must remain false

## `real_validated_live`
- deliveryTrack: `experimental`
- officialRuntimeLane: `False`
- intendedProductLine: `validated_live`
- effectivePublicRuntimeTier: `preview`
- taskWorkbenchVisible: `False`
- taskExecutionInteractive: `False`
- acceptance checks:
  - delivery track must remain experimental
  - planning_capability must remain validated_live or live-candidate scoped
  - hardware_execution_mode must remain ros2_control_live or candidate live equivalent
  - public tier must fail closed to preview until promotion is effective
- required evidence:
  - `validated_live_backbone_declared`
  - `target_runtime_gate_passed`
  - `hil_gate_passed`
  - `release_checklist_signed`

## `sim_authoritative`
- deliveryTrack: `official_active`
- officialRuntimeLane: `True`
- intendedProductLine: `validated_sim`
- effectivePublicRuntimeTier: `validated_sim`
- taskWorkbenchVisible: `True`
- taskExecutionInteractive: `True`
- acceptance checks:
  - public tier must be validated_sim
  - planning_capability must be validated_sim
  - hardware_execution_mode must be authoritative_simulation
  - forward_hardware_commands must remain true
  - task execution must be interactive

## `sim_perception_preview`
- deliveryTrack: `official_active`
- officialRuntimeLane: `True`
- intendedProductLine: `preview`
- effectivePublicRuntimeTier: `preview`
- taskWorkbenchVisible: `False`
- taskExecutionInteractive: `False`
- acceptance checks:
  - public tier must remain preview
  - task execution must stay non-interactive
  - forward_hardware_commands must remain false

## `sim_preview`
- deliveryTrack: `official_active`
- officialRuntimeLane: `True`
- intendedProductLine: `preview`
- effectivePublicRuntimeTier: `preview`
- taskWorkbenchVisible: `False`
- taskExecutionInteractive: `False`
- acceptance checks:
  - public tier must remain preview
  - task execution must stay non-interactive
  - forward_hardware_commands must remain false

