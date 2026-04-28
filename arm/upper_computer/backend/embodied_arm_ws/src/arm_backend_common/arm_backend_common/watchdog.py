from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Watchdog:
    timeout_seconds: float
    last_tick: float = field(default_factory=time.monotonic)

    def tick(self) -> None:
        self.last_tick = time.monotonic()

    def expired(self) -> bool:
        return (time.monotonic() - self.last_tick) > self.timeout_seconds

    def age(self) -> float:
        return time.monotonic() - self.last_tick
