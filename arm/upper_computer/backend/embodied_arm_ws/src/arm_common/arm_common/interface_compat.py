from __future__ import annotations

"""Canonical imports for ROS2 interfaces.

The active runtime stack resolves message, service, and action contracts from
``arm_interfaces`` only. Deprecated mirror packages remain in the repository for
legacy consumers and mirror-verification tests, but the active stack no longer
falls back to them at runtime.
"""

from importlib import import_module
from types import ModuleType
from typing import Iterable


_ACTIVE_PACKAGE: str | None = None


def _load(kind: str) -> ModuleType:
    return import_module(f'arm_interfaces.{kind}')


def _resolve(kind: str, names: Iterable[str]) -> tuple:
    global _ACTIVE_PACKAGE
    try:
        module = _load(kind)
        values = tuple(getattr(module, name) for name in names)
        _ACTIVE_PACKAGE = 'arm_interfaces'
        return values
    except Exception:  # pragma: no cover - depends on ROS environment
        _ACTIVE_PACKAGE = None
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
    HomeArm, ResetFault, SetMode, StartTask, StopTask, ActivateCalibrationVersion, RuntimeSceneSnapshot, RuntimeGraspPlan = _resolve(
        'srv', ('HomeArm', 'ResetFault', 'SetMode', 'StartTask', 'StopTask', 'ActivateCalibrationVersion', 'RuntimeSceneSnapshot', 'RuntimeGraspPlan')
    )


class ActionTypes:
    PickPlaceTask, Homing, Recover, ManualServo, HomeSequence = _resolve(
        'action', ('PickPlaceTask', 'Homing', 'Recover', 'ManualServo', 'HomeSequence')
    )


__all__ = ['MsgTypes', 'SrvTypes', 'ActionTypes', '_ACTIVE_PACKAGE']


def active_interface_package() -> str | None:
    return _ACTIVE_PACKAGE
