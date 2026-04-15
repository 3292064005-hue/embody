# Control Lane Migration

## Canonical launch entry points

- `ros2 launch arm_bringup runtime.launch.py runtime_lane:=sim_preview`
- `ros2 launch arm_bringup runtime.launch.py runtime_lane:=sim_authoritative`
- `ros2 launch arm_bringup runtime.launch.py runtime_lane:=real_preview`
- `ros2 launch arm_bringup runtime_live_control.launch.py`
- `ros2 launch arm_bringup runtime_real_validated_live.launch.py`
- `ros2 launch arm_bringup runtime_real_authoritative.launch.py` *(retired wrapper; requires `EMBODIED_ARM_ALLOW_LEGACY_LIVE_ALIASES=true` or it fails fast and instructs callers to switch to `live_control` / `experimental_*`)*

## live_control / real_validated_live semantics

`live_control` is the validated-live candidate lane; `real_validated_live` is the promotion-controlled validated lane, not an unconditional live-production lane. It is only promoted above preview tier when all of the following are true:

1. `planning_capability=validated_live`
2. a live planning backend is explicitly injected into `MoveItClient`
3. readiness reports `planner_ready=true`
4. command policy allows `startTask`
5. hardware transport is not simulated
6. `config/runtime_promotion_receipts.yaml` commits `validated_live.promoted=true` with traceable evidence

If any of the above is false, the lane remains preview-tier and task execution stays non-interactive. This is a deliberate fail-closed contract to avoid representing unavailable live planning as operator-ready.

## Rollback

To roll back from `live_control` / `real_validated_live`, switch back to:

- `real_preview` for live camera / hardware preview work
- `sim_authoritative` for fully validated simulation execution

No code change is required; lane selection alone is sufficient.

- `ros2 launch arm_bringup runtime_live_control.launch.py` *(canonical experimental candidate lane)*
