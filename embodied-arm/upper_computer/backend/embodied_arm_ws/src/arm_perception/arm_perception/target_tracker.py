from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional
import time
from arm_backend_common.data_models import TargetSnapshot


@dataclass
class TrackedTarget:
    """Tracked target state held by :class:`TargetTracker`."""

    snapshot: TargetSnapshot
    first_seen: float
    last_seen: float
    seen_count: int = 1


class TargetTracker:
    """Track, age, and rank perception targets across frames."""

    def __init__(self, stale_after_sec: float = 1.5, min_seen_count: int = 1) -> None:
        """Initialize the tracker.

        Args:
            stale_after_sec: Time before a target is pruned.
            min_seen_count: Minimum observations required for graspability.

        Returns:
            None.

        Raises:
            ValueError: If configuration values are invalid.
        """
        if stale_after_sec <= 0.0:
            raise ValueError('stale_after_sec must be positive')
        if min_seen_count <= 0:
            raise ValueError('min_seen_count must be positive')
        self.stale_after_sec = float(stale_after_sec)
        self.min_seen_count = int(min_seen_count)
        self._targets: Dict[str, TrackedTarget] = {}

    def upsert(self, target: TargetSnapshot, now: float | None = None) -> None:
        """Upsert a tracked target.

        Args:
            target: Target snapshot to track.
            now: Optional monotonic timestamp.

        Returns:
            None.

        Raises:
            ValueError: If ``target`` is invalid.
        """
        if not isinstance(target, TargetSnapshot):
            raise ValueError('target must be a TargetSnapshot instance')
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

    def ingest_batch(self, targets: Iterable[TargetSnapshot], now: float | None = None) -> None:
        """Ingest a batch of target snapshots.

        Args:
            targets: Iterable of targets.
            now: Optional monotonic timestamp.

        Returns:
            None.

        Raises:
            ValueError: If a batch item is invalid.
        """
        now = time.monotonic() if now is None else now
        for target in targets:
            self.upsert(target, now=now)
        self.prune(now=now)

    def prune(self, now: float | None = None) -> int:
        """Prune stale targets.

        Args:
            now: Optional monotonic timestamp.

        Returns:
            int: Number of pruned targets.

        Raises:
            Does not raise.
        """
        now = time.monotonic() if now is None else now
        expired = [key for key, value in self._targets.items() if now - value.last_seen > self.stale_after_sec]
        for key in expired:
            self._targets.pop(key, None)
        return len(expired)

    def get_graspable(self, now: float | None = None) -> list[TargetSnapshot]:
        """Return graspable targets sorted by confidence.

        Args:
            now: Optional monotonic timestamp.

        Returns:
            list[TargetSnapshot]: Graspable targets.

        Raises:
            Does not raise.
        """
        if now is not None:
            self.prune(now)
        values = [item.snapshot for item in self._targets.values() if item.snapshot.confidence >= 0.5 and item.seen_count >= self.min_seen_count]
        values.sort(key=lambda item: (-item.confidence, item.key()))
        return values

    def select(self, selector: str, *, exclude_keys: Iterable[str] | None = None, now: float | None = None) -> Optional[TargetSnapshot]:
        """Select the best graspable target matching a selector.

        Args:
            selector: Target selector string.
            exclude_keys: Optional target keys to skip.
            now: Optional monotonic timestamp.

        Returns:
            Optional[TargetSnapshot]: Matching target or ``None``.

        Raises:
            Does not raise.
        """
        excluded = set(exclude_keys or ())
        for target in self.get_graspable(now):
            if target.key() in excluded:
                continue
            if target.matches_selector(selector):
                return target
        return None

    def best_target(self, selector: str = '', *, exclude_keys: Iterable[str] | None = None, now: float | None = None) -> Optional[TargetSnapshot]:
        """Return the best currently graspable target."""
        return self.select(selector, exclude_keys=exclude_keys, now=now)

    def health_snapshot(self, now: float | None = None) -> dict[str, object]:
        """Return tracker-derived availability metrics.

        Args:
            now: Optional monotonic timestamp.

        Returns:
            dict[str, object]: Availability metrics.

        Raises:
            Does not raise.
        """
        if now is not None:
            self.prune(now)
        return {'targetAvailable': bool(self.get_graspable(now)), 'trackedTargetCount': len(self._targets), 'graspableTargetCount': len(self.get_graspable(now))}

    def snapshot(self, now: float | None = None) -> list[dict[str, object]]:
        """Return a serializable tracked-target snapshot.

        Args:
            now: Optional monotonic timestamp.

        Returns:
            list[dict[str, object]]: Tracked target snapshot.

        Raises:
            Does not raise.
        """
        if now is not None:
            self.prune(now)
        now = time.monotonic() if now is None else now
        data: list[dict[str, object]] = []
        for item in self._targets.values():
            data.append({'key': item.snapshot.key(), 'seenCount': item.seen_count, 'ageSec': max(0.0, now - item.last_seen), 'target': item.snapshot.to_dict()})
        data.sort(key=lambda item: (-(item['target']['confidence']), item['key']))
        return data


VisionTargetTracker = TargetTracker
