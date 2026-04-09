from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional

from arm_backend_common.data_models import TargetSnapshot


@dataclass
class Reservation:
    owner_task_id: str
    target_key: str
    expires_at: float


class TargetReservationManager:
    def __init__(self, reserve_timeout_sec: float = 3.0) -> None:
        self.reserve_timeout_sec = reserve_timeout_sec
        self._reservations: Dict[str, Reservation] = {}

    def _cleanup(self, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        expired_keys = [key for key, res in self._reservations.items() if res.expires_at <= now]
        for key in expired_keys:
            self._reservations.pop(key, None)

    def reserve(self, task_id: str, target: TargetSnapshot, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        self._cleanup(now)
        key = target.key()
        held = self._reservations.get(key)
        if held and held.owner_task_id != task_id:
            return False
        self._reservations[key] = Reservation(owner_task_id=task_id, target_key=key, expires_at=now + self.reserve_timeout_sec)
        return True

    def refresh(self, task_id: str, target: Optional[TargetSnapshot], now: Optional[float] = None) -> None:
        if target is None:
            return
        self.reserve(task_id, target, now=now)

    def release(self, task_id: str, target: Optional[TargetSnapshot]) -> None:
        if target is None:
            return
        key = target.key()
        held = self._reservations.get(key)
        if held and held.owner_task_id == task_id:
            self._reservations.pop(key, None)

    def is_reserved(self, target: TargetSnapshot, now: Optional[float] = None) -> bool:
        self._cleanup(now)
        return target.key() in self._reservations
