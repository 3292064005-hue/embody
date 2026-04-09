from __future__ import annotations

from typing import Dict, Iterable, Optional

from arm_backend_common.data_models import TargetSnapshot


class TargetRegistry:
    def __init__(self) -> None:
        self._targets: Dict[str, TargetSnapshot] = {}

    def upsert(self, target: TargetSnapshot) -> None:
        self._targets[target.key()] = target

    def latest(self) -> Optional[TargetSnapshot]:
        if not self._targets:
            return None
        return max(self._targets.values(), key=lambda target: target.received_monotonic)

    def find_matching(self, selector: str, stale_target_sec: float, now: float) -> Iterable[TargetSnapshot]:
        selector = selector.strip().lower()
        candidates = [target for target in self._targets.values() if target.is_fresh(stale_target_sec, now=now)]
        candidates.sort(key=lambda target: target.received_monotonic, reverse=True)
        if not selector:
            return candidates
        return [target for target in candidates if target.matches_selector(selector)]

    def mark_consumed(self, key: str) -> None:
        self._targets.pop(key, None)
