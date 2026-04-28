from __future__ import annotations

from typing import Any

from arm_backend_common.config import load_yaml
from arm_backend_common.data_models import TaskProfile


def build_task_profile(current: TaskProfile, payload: dict[str, Any], *, place_profiles: dict[str, Any] | None = None) -> TaskProfile:
    """Build a TaskProfile from user/runtime payload while preserving defaults."""
    profiles = place_profiles if place_profiles is not None else payload.get('place_profiles', {})
    return TaskProfile(
        confidence_threshold=float(payload.get('confidence_threshold', current.confidence_threshold)),
        stale_target_sec=float(payload.get('stale_target_sec', current.stale_target_sec)),
        verify_timeout_sec=float(payload.get('verify_timeout_sec', current.verify_timeout_sec)),
        verify_strategy=str(payload.get('verify_strategy', current.verify_strategy)),
        clear_table_max_items=int(payload.get('clear_table_max_items', current.clear_table_max_items)),
        ack_timeout_sec=float(payload.get('ack_timeout_sec', current.ack_timeout_sec)),
        completion_timeout_sec=float(payload.get('completion_timeout_sec', current.completion_timeout_sec)),
        selector_to_place_profile={str(k): str(v) for k, v in dict(profiles).items()},
    )


def load_task_profile_from_yaml(path: str, current: TaskProfile) -> TaskProfile:
    payload = dict(load_yaml(path).data)
    return build_task_profile(current, payload, place_profiles=payload.get('place_profiles', {}))


def load_task_profile_from_active_profiles(payload: dict[str, Any], current: TaskProfile) -> TaskProfile | None:
    task_profile = payload.get('task_profile', {})
    place_profiles = payload.get('placement_profiles', {})
    if not task_profile:
        return None
    merged = dict(task_profile)
    merged['place_profiles'] = place_profiles
    return build_task_profile(current, merged, place_profiles=place_profiles)
