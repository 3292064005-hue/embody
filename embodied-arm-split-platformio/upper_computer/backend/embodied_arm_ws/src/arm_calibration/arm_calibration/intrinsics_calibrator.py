from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class IntrinsicsCalibrationResult:
    rms_error: float
    frame_count: int


class IntrinsicsCalibrator:
    def calibrate(self, frames: Iterable[object]) -> IntrinsicsCalibrationResult:
        count = sum(1 for _ in frames)
        return IntrinsicsCalibrationResult(rms_error=0.0 if count else 1.0, frame_count=count)
