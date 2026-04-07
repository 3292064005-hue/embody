from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, Optional
import time
from arm_backend_common.data_models import TargetSnapshot

@dataclass
class TrackedTarget:
    snapshot: TargetSnapshot
    first_seen: float
    last_seen: float
    seen_count: int = 1

class VisionTargetTracker:
    def __init__(self, stale_after_sec: float = 1.5, min_seen_count: int = 1) -> None:
        self.stale_after_sec = stale_after_sec
        self.min_seen_count = max(1, int(min_seen_count))
        self._targets: Dict[str, TrackedTarget] = {}

    def upsert(self, target: TargetSnapshot, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        key = target.key()
        current = self._targets.get(key)
        if current is None:
            self._targets[key] = TrackedTarget(snapshot=target, first_seen=now, last_seen=now)
            return
        moved = target.moved_from(current.snapshot)
        target.version = max(current.snapshot.version + 1, target.version)
        current.snapshot = target
        current.last_seen = now
        if moved:
            current.first_seen = now
            current.seen_count = 1
        else:
            current.seen_count += 1

    def prune(self, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        expired = [key for key, value in self._targets.items() if now - value.last_seen > self.stale_after_sec]
        for key in expired:
            self._targets.pop(key, None)
        return len(expired)

    def get_graspable(self, now: float | None = None) -> list[TargetSnapshot]:
        if now is not None:
            self.prune(now)
        values = [
            item.snapshot
            for item in self._targets.values()
            if item.snapshot.confidence >= 0.5 and item.seen_count >= self.min_seen_count
        ]
        values.sort(key=lambda item: (-item.confidence, item.key()))
        return values

    def select(self, selector: str, *, exclude_keys: Iterable[str] | None = None, now: float | None = None) -> Optional[TargetSnapshot]:
        excluded = set(exclude_keys or ())
        for target in self.get_graspable(now):
            if target.key() in excluded:
                continue
            if target.matches_selector(selector):
                return target
        return None

    def snapshot(self, now: float | None = None) -> list[dict[str, object]]:
        if now is not None:
            self.prune(now)
        now = time.monotonic() if now is None else now
        data: list[dict[str, object]] = []
        for item in self._targets.values():
            data.append({
                'key': item.snapshot.key(),
                'seenCount': item.seen_count,
                'ageSec': max(0.0, now - item.last_seen),
                'target': item.snapshot.to_dict(),
            })
        data.sort(key=lambda item: (-(item['target']['confidence']), item['key']))
        return data
