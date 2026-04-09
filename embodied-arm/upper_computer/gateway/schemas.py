from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TaskTypeLiteral = Literal['pick_place', 'sort_by_color', 'sort_by_qr', 'clear_table']
TargetCategoryLiteral = Literal['red', 'blue', 'green', 'qr_a', 'qr_b', 'qr_c']


class ErrorEnvelope(BaseModel):
    """Stable error response payload."""

    code: int
    error: str
    failureClass: str | None = None
    message: str
    requestId: str
    timestamp: str
    detail: str
    operatorActionable: bool | None = None


class StartTaskRequest(BaseModel):
    templateId: str | None = Field(default=None, min_length=1)
    taskType: TaskTypeLiteral = Field(default='pick_place')
    targetCategory: TargetCategoryLiteral | None = None


class CalibrationRoi(BaseModel):
    x: int = Field(default=0, ge=0)
    y: int = Field(default=0, ge=0)
    width: int = Field(default=640, gt=0)
    height: int = Field(default=480, gt=0)


class CalibrationOffsets(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @field_validator('x', 'y', 'z')
    @classmethod
    def _validate_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError('offset must be finite')
        return float(value)


class CalibrationProfileRequest(BaseModel):
    profileName: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9._-]+$', default='default')
    roi: CalibrationRoi = Field(default_factory=CalibrationRoi)
    tableScaleMmPerPixel: float = Field(default=1.0, gt=0)
    offsets: CalibrationOffsets = Field(default_factory=CalibrationOffsets)

    @field_validator('tableScaleMmPerPixel')
    @classmethod
    def _validate_scale(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError('tableScaleMmPerPixel must be finite')
        return float(value)


class GripperRequest(BaseModel):
    open: bool = True


class JogJointRequest(BaseModel):
    jointIndex: int = Field(ge=0, le=5)
    direction: Literal[-1, 1] = 1
    stepDeg: float = Field(gt=0.0, le=10.0, default=2.0)


class ServoCartesianRequest(BaseModel):
    axis: Literal['x', 'y', 'z', 'rx', 'ry', 'rz']
    delta: float = Field(ge=-0.1, le=0.1)


class SetModeRequest(BaseModel):
    mode: Literal['idle', 'manual', 'task', 'maintenance']
