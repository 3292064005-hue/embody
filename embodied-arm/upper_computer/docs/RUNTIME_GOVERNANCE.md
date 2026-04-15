# Runtime Governance

## Delivery tracks

- `official_active`: `sim_preview`, `sim_perception_preview`, `real_preview`, `hybrid_preview`, `hw_preview`, `full_demo_preview`, `sim_authoritative`, `full_demo_authoritative`
- `experimental`: `live_control`, `real_validated_live`

## Rules

1. `backend/embodied_arm_ws/src/arm_bringup/config/runtime_authority.yaml` is the only editable source of runtime governance.
2. Generated runtime contracts must list only `official_active` lanes under product-line lane exposure.
3. Experimental live lanes stay runnable only through explicit canonical names or `experimental_*` aliases.
4. New operator-facing features, task templates, and release checks must attach to `official_active` unless a promotion decision is made first.

## Migration / rollback

- Existing compatibility aliases remain available.
- Rolling back this governance split only requires restoring the previous runtime authority and regenerating derived artifacts.
