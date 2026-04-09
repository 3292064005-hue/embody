from __future__ import annotations

import datetime as _dt
import os
from typing import Any

_DEFAULT_STALE_AFTER_SEC = 1.2


def readiness_stale_after_sec() -> float:
    """Return the gateway-side readiness freshness budget in seconds.

    The default intentionally mirrors the backend task orchestrator's
    ``hardware_fresh_sec`` default so gateway-side admission stays aligned with
    ROS-native admission. Operators may override the value with
    ``EMBODIED_ARM_READINESS_STALE_SEC`` for deployment-specific tuning.
    """
    raw = os.environ.get('EMBODIED_ARM_READINESS_STALE_SEC', str(_DEFAULT_STALE_AFTER_SEC))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(_DEFAULT_STALE_AFTER_SEC)
    return max(0.0, value)



def readiness_updated_at_age_sec(readiness: dict[str, Any] | None, *, now: _dt.datetime | None = None) -> float:
    """Return the age of one readiness snapshot in seconds.

    Returns ``float('inf')`` when the payload is missing or the timestamp cannot
    be parsed, which makes callers fail closed.
    """
    if not isinstance(readiness, dict):
        return float('inf')
    updated_at = readiness.get('updatedAt')
    if not updated_at:
        return float('inf')
    try:
        parsed = _dt.datetime.fromisoformat(str(updated_at).replace('Z', '+00:00'))
    except Exception:
        return float('inf')
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    reference = now or _dt.datetime.now(_dt.timezone.utc)
    age = (reference - parsed.astimezone(_dt.timezone.utc)).total_seconds()
    return max(0.0, float(age))



def readiness_snapshot_is_stale(readiness: dict[str, Any] | None, *, stale_after_sec: float | None = None) -> bool:
    """Return whether an authoritative readiness snapshot must be treated as stale.

    Non-authoritative snapshots (for example gateway bootstrap or explicit dev
    simulated-local-only mode) are not rejected by age because they are gateway
    owned fallbacks rather than backend truth projections.
    """
    if not isinstance(readiness, dict):
        return True
    if not bool(readiness.get('authoritative', False)):
        return False
    threshold = readiness_stale_after_sec() if stale_after_sec is None else max(0.0, float(stale_after_sec))
    if threshold <= 0.0:
        return False
    return readiness_updated_at_age_sec(readiness) > threshold



def readiness_stale_reason() -> str:
    """Stable fail-closed reason for stale authoritative readiness snapshots."""
    return 'authoritative readiness snapshot stale'
