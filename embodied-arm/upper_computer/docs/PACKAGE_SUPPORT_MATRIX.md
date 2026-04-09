# Package Support Matrix

This matrix is the human-readable companion to the active runtime lane and deprecation rules.

| Package set | Status | Included in active runtime lane | Rule |
| --- | --- | --- | --- |
| `arm_profiles`, `arm_calibration`, `arm_hardware_bridge`, `arm_readiness_manager`, `arm_safety_supervisor`, `arm_camera_driver`, `arm_perception`, `arm_scene_manager`, `arm_grasp_planner`, `arm_motion_planner`, `arm_motion_executor`, `arm_task_orchestrator`, `arm_bt_runtime`, `arm_bt_nodes`, `arm_diagnostics`, `arm_logger` | runtime-core | yes | new runtime features must land here or in supervision; authoritative lanes consume scene/grasp through `runtime_service` |
| `arm_lifecycle_manager` | runtime-supervision | yes | supervision only; do not carry compatibility business logic; autostart completion does not end runtime health monitoring |
| `arm_common`, `arm_interfaces`, `arm_mock_tools`, `arm_sim`, `arm_tools`, `arm_tests` | runtime-support | yes (gate only) | shared support packages may participate in active-lane testing and contract validation, but they are not product-line runtime-core modules |
| `arm_task_manager`, `arm_motion_bridge`, `arm_vision` | compatibility / deprecated | no | kept only for compatibility and regression containment; do not add new feature work |
| `arm_esp32_gateway` | runtime-core | yes | board HTTP health / status / voice ingress is now part of the active runtime lane and release gate |
| `arm_hmi` | experimental | no | UI-side experimentation must stay out of the active runtime lane and release gate unless explicitly promoted |

## Enforcement points

- `pytest-active.ini` exposes runtime-core + runtime-supervision packages, plus the minimal runtime-support set required for active-lane tests and contract validation.
- `backend/embodied_arm_ws/active_profile_quarantine.json` tracks every intentionally ignored active-lane test.
- `python scripts/check_active_profile_consistency.py` fails if active-lane exposure or ignore lists drift.
- authoritative runtime lanes must keep provider truth (`embedded_core` vs `runtime_service`) aligned across `runtime_profiles.yaml`, generated runtime contracts, gateway projection, and frontend runtime feature guards.
- supervision health is a runtime contract, not a one-shot bringup event; losing an active managed node after autostart remains release-gated behavior.
