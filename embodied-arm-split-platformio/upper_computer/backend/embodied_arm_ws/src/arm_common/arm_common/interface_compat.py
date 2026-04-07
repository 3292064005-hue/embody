from __future__ import annotations

"""Compatibility imports for ROS2 interfaces.

Prefer ``arm_interfaces`` and fall back to the deprecated ``arm_msgs`` mirror
while the migration is still in progress.
"""

from importlib import import_module
from types import ModuleType
from typing import Iterable


_ACTIVE_PACKAGE: str | None = None


def _load(package: str, kind: str) -> ModuleType:
    return import_module(f'{package}.{kind}')


def _resolve(kind: str, names: Iterable[str]) -> tuple:
    global _ACTIVE_PACKAGE
    last_error: Exception | None = None
    for package in ('arm_interfaces', 'arm_msgs'):
        try:
            module = _load(package, kind)
            values = tuple(getattr(module, name) for name in names)
            _ACTIVE_PACKAGE = package
            return values
        except Exception as exc:  # pragma: no cover - depends on ROS environment
            last_error = exc
    return tuple(object for _ in names)


class MsgTypes:
    (
        HardwareState,
        SystemState,
        TargetInfo,
        TaskEvent,
        FaultReport,
        ReadinessState,
        TaskStatus,
        DiagnosticsSummary,
        CalibrationProfileMsg,
        TargetArray,
        BringupStatus,
    ) = _resolve(
        'msg',
        (
            'HardwareState',
            'SystemState',
            'TargetInfo',
            'TaskEvent',
            'FaultReport',
            'ReadinessState',
            'TaskStatus',
            'DiagnosticsSummary',
            'CalibrationProfileMsg',
            'TargetArray',
            'BringupStatus',
        ),
    )


class SrvTypes:
    HomeArm, ResetFault, SetMode, StartTask, StopTask, ActivateCalibrationVersion = _resolve(
        'srv', ('HomeArm', 'ResetFault', 'SetMode', 'StartTask', 'StopTask', 'ActivateCalibrationVersion')
    )


class ActionTypes:
    PickPlaceTask, Homing, Recover, ManualServo, HomeSequence = _resolve(
        'action', ('PickPlaceTask', 'Homing', 'Recover', 'ManualServo', 'HomeSequence')
    )


__all__ = ['MsgTypes', 'SrvTypes', 'ActionTypes', '_ACTIVE_PACKAGE']


def active_interface_package() -> str | None:
    return _ACTIVE_PACKAGE
