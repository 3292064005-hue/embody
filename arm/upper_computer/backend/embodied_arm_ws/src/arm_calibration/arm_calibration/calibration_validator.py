from __future__ import annotations


class CalibrationValidator:
    def validate(self, residual_px: float, residual_mm: float, px_threshold: float, mm_threshold: float) -> dict:
        ok = residual_px <= px_threshold and residual_mm <= mm_threshold
        return {'ok': ok, 'residual_px': float(residual_px), 'residual_mm': float(residual_mm)}
