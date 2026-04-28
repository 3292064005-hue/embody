from __future__ import annotations

"""Runtime readiness state and projection helpers.

The authoritative readiness contract is defined in :mod:`contract_defs`. This
module owns runtime freshness tracking, state mutation, and serialization of the
public readiness snapshot consumed by the gateway and frontend.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable
import time

from .contract_defs import (
    DEFAULT_READINESS_CHECKS,
    DEFAULT_STALE_AFTER,
    READINESS_REQUIRED_BY_MODE,
    RUNTIME_HEALTH_REQUIRED,
    build_command_policies,
    build_command_summary,
    required_checks_for_mode,
)


@dataclass
class ReadinessCheck:
    """Single readiness check state.

    Attributes:
        name: Stable readiness check name.
        ok: Raw health flag before stale handling.
        detail: Human-readable detail string.
        stale_after_sec: Optional stale timeout.
        updated_monotonic: Monotonic timestamp of the latest refresh.
    """

    name: str
    ok: bool = False
    detail: str = 'not_ready'
    stale_after_sec: float | None = None
    updated_monotonic: float = field(default_factory=time.monotonic)

    def refresh(self, ok: bool, detail: str, stale_after_sec: float | None = None) -> None:
        """Update the readiness check with a new health report.

        Args:
            ok: Raw health flag.
            detail: Human-readable detail string.
            stale_after_sec: Optional stale timeout override.

        Returns:
            None.

        Raises:
            Does not raise.

        Boundary behavior:
            Non-positive stale values disable stale handling for the check.
        """
        self.ok = bool(ok)
        self.detail = detail
        if stale_after_sec is not None:
            self.stale_after_sec = None if stale_after_sec <= 0.0 else float(stale_after_sec)
        self.updated_monotonic = time.monotonic()

    def age_sec(self, now: float | None = None) -> float:
        """Return the age of the latest update in seconds."""
        now = time.monotonic() if now is None else now
        return max(0.0, now - self.updated_monotonic)

    def is_stale(self, now: float | None = None) -> bool:
        """Return whether the check has exceeded its freshness budget."""
        if self.stale_after_sec is None:
            return False
        return self.age_sec(now) > self.stale_after_sec

    def effective_ok(self, now: float | None = None) -> bool:
        """Return the effective readiness result after stale handling."""
        return self.ok and not self.is_stale(now)


@dataclass
class ReadinessSnapshot:
    """Serializable runtime readiness snapshot.

    Attributes:
        checks: Readiness checks keyed by stable check name.
        mode: Effective public readiness mode.
        required: Required checks for the current mode.
        controller_mode: Public controller mode projection.
        runtime_phase: Public runtime phase projection.
        task_stage: Public task-stage projection.
    """

    checks: Dict[str, ReadinessCheck]
    mode: str = 'boot'
    required: tuple[str, ...] = ()
    controller_mode: str = 'idle'
    runtime_phase: str = 'boot'
    task_stage: str = 'created'

    @staticmethod
    def _missing_names(required: Iterable[str], checks: Dict[str, ReadinessCheck], now: float) -> list[str]:
        missing: list[str] = []
        for name in required:
            check = checks.get(name, ReadinessCheck(name=name))
            if not check.effective_ok(now):
                missing.append(name)
        return missing

    def _public_checks(self, now: float) -> dict[str, dict[str, Any]]:
        return {
            name: {
                'ok': item.ok,
                'effectiveOk': item.effective_ok(now),
                'detail': item.detail,
                'ageSec': item.age_sec(now),
                'stale': item.is_stale(now),
                'staleAfterSec': item.stale_after_sec,
            }
            for name, item in self.checks.items()
        }

    @property
    def runtime_healthy(self) -> bool:
        now = time.monotonic()
        return not self._missing_names(RUNTIME_HEALTH_REQUIRED, self.checks, now)

    @property
    def mode_ready(self) -> bool:
        return bool(self.required) and all(self.checks.get(name, ReadinessCheck(name=name)).effective_ok() for name in self.required)

    @property
    def all_ready(self) -> bool:
        return self.mode_ready

    def missing(self) -> list[str]:
        now = time.monotonic()
        return self._missing_names(self.required, self.checks, now)

    def runtime_missing(self) -> list[str]:
        now = time.monotonic()
        return self._missing_names(RUNTIME_HEALTH_REQUIRED, self.checks, now)

    def missing_details(self) -> list[dict[str, str]]:
        details: list[dict[str, str]] = []
        now = time.monotonic()
        for name in self.required:
            check = self.checks.get(name, ReadinessCheck(name=name))
            if check.effective_ok(now):
                continue
            details.append({'name': name, 'detail': 'stale' if check.is_stale(now) else check.detail})
        return details

    def command_policies(self) -> dict[str, dict[str, Any]]:
        """Return command policies derived from the authoritative contract.

        Returns:
            Mapping keyed by public command name.

        Raises:
            Does not raise.

        Boundary behavior:
            Missing checks are treated as not-ready; policy calculation uses the
            current public readiness mode rather than any private runtime enum.
        """
        return build_command_policies(self.mode, self._public_checks(time.monotonic()))

    def command_summary(self) -> dict[str, Any]:
        return build_command_summary(self.command_policies())

    def as_dict(self) -> dict:
        """Serialize the readiness snapshot to a transport-safe dictionary.

        Returns:
            dict: Public readiness payload for ROS, gateway, and frontend consumers.

        Raises:
            Does not raise.

        Boundary behavior:
            Missing checks are emitted with conservative non-ready defaults.
        """
        now = time.monotonic()
        checks = self._public_checks(now)
        policies = build_command_policies(self.mode, checks)
        return {
            'mode': self.mode,
            'controllerMode': self.controller_mode,
            'runtimePhase': self.runtime_phase,
            'taskStage': self.task_stage,
            'runtimeHealthy': self.runtime_healthy,
            'modeReady': self.mode_ready,
            'allReady': self.all_ready,
            'requiredChecks': list(self.required),
            'runtimeRequiredChecks': list(RUNTIME_HEALTH_REQUIRED),
            'missingChecks': self.missing(),
            'runtimeMissingChecks': self.runtime_missing(),
            'missingDetails': self.missing_details(),
            'checks': checks,
            'commandPolicies': policies,
            'commandSummary': build_command_summary(policies),
        }


class ReadinessManager:
    """Track runtime readiness checks and build public snapshots."""

    DEFAULT_CHECKS = DEFAULT_READINESS_CHECKS
    DEFAULT_STALE_AFTER = DEFAULT_STALE_AFTER
    REQUIRED_BY_MODE = READINESS_REQUIRED_BY_MODE

    def __init__(self, checks: Iterable[str] | None = None) -> None:
        """Initialize the readiness manager.

        Args:
            checks: Optional explicit readiness check names.

        Returns:
            None.

        Raises:
            Does not raise.

        Boundary behavior:
            Unknown check names are accepted and default to non-stale tracking.
        """
        names = tuple(checks or self.DEFAULT_CHECKS)
        self._checks = {name: ReadinessCheck(name=name, stale_after_sec=self.DEFAULT_STALE_AFTER.get(name)) for name in names}
        self._mode = 'boot'
        self._controller_mode = 'idle'
        self._runtime_phase = 'boot'
        self._task_stage = 'created'

    def update(self, name: str, ok: bool, detail: str, stale_after_sec: float | None = None) -> None:
        """Update a single readiness check.

        Args:
            name: Stable readiness check name.
            ok: Raw health flag.
            detail: Human-readable detail string.
            stale_after_sec: Optional freshness override.

        Returns:
            None.

        Raises:
            Does not raise.

        Boundary behavior:
            New check names are added dynamically so upstream publishers can be
            introduced without crashing the readiness manager.
        """
        if name not in self._checks:
            self._checks[name] = ReadinessCheck(name=name)
        self._checks[name].refresh(ok, detail, stale_after_sec)

    def bulk_update(self, values: dict[str, tuple[bool, str] | tuple[bool, str, float | None]]) -> None:
        """Apply a batch of readiness check updates.

        Args:
            values: Mapping from check name to `(ok, detail[, stale_after_sec])`.

        Returns:
            None.

        Raises:
            ValueError: When a payload tuple length is unsupported.

        Boundary behavior:
            Each update is applied independently, so one new key does not prevent
            the rest of the batch from being committed.
        """
        for name, value in values.items():
            if len(value) == 2:
                ok, detail = value
                self.update(name, ok, detail)
            elif len(value) == 3:
                ok, detail, stale_after_sec = value
                self.update(name, ok, detail, stale_after_sec)
            else:
                raise ValueError(f'unsupported readiness update payload for {name!r}: {value!r}')

    def set_mode(self, mode: str) -> None:
        self._mode = str(mode or 'boot').strip().lower() or 'boot'

    def set_semantics(self, *, controller_mode: str | None = None, runtime_phase: str | None = None, task_stage: str | None = None) -> None:
        if controller_mode is not None:
            self._controller_mode = str(controller_mode or 'idle').strip().lower() or 'idle'
        if runtime_phase is not None:
            self._runtime_phase = str(runtime_phase or 'boot').strip().lower() or 'boot'
        if task_stage is not None:
            self._task_stage = str(task_stage or 'created').strip().lower() or 'created'


    def is_ready_for_task(self) -> tuple[bool, str]:
        """Return whether the runtime is ready for task execution.

        Returns:
            tuple[bool, str]: `(ready, reason)` pair.

        Raises:
            Does not raise.

        Boundary behavior:
            When the runtime mode has not been explicitly set, the function still
            evaluates readiness against the authoritative `task` requirements.
        """
        task_required = tuple(name for name in required_checks_for_mode('task') if name in self._checks)
        task_snapshot = ReadinessSnapshot(
            checks=self._checks,
            mode='task',
            required=task_required,
            controller_mode=self._controller_mode,
            runtime_phase=self._runtime_phase,
            task_stage=self._task_stage,
        )
        if task_snapshot.mode_ready:
            return True, 'ready'
        missing = task_snapshot.missing()
        if missing:
            return False, f"missing readiness: {', '.join(missing)}"
        return False, 'task runtime not ready'


    def is_ready_for_manual(self) -> tuple[bool, str]:
        """Return whether the runtime is ready for manual/maintenance control.

        Returns:
            tuple[bool, str]: `(ready, reason)` pair.

        Raises:
            Does not raise.

        Boundary behavior:
            The method evaluates the authoritative `manual` requirements directly,
            independent of the current public runtime mode token.
        """
        manual_required = tuple(name for name in required_checks_for_mode('manual') if name in self._checks)
        manual_snapshot = ReadinessSnapshot(
            checks=self._checks,
            mode='manual',
            required=manual_required,
            controller_mode=self._controller_mode,
            runtime_phase=self._runtime_phase,
            task_stage=self._task_stage,
        )
        if manual_snapshot.mode_ready:
            return True, 'ready'
        missing = manual_snapshot.missing()
        if missing:
            return False, f"missing readiness: {', '.join(missing)}"
        return False, 'manual runtime not ready'

    def snapshot(self, mode: str | None = None) -> ReadinessSnapshot:
        """Build a public readiness snapshot from the current runtime state.

        Args:
            mode: Optional public readiness mode override kept for backward
                compatibility with older direct-call sites and regression tests.

        Returns:
            ReadinessSnapshot: Serializable public readiness projection.

        Raises:
            Does not raise.

        Boundary behavior:
            Unknown modes degrade to the authoritative ``task`` requirement set.
            Passing ``None`` preserves the manager's currently tracked public mode.
        """
        effective_mode = str(mode or self._mode or 'boot').strip().lower()
        normalized_mode = effective_mode if effective_mode in self.REQUIRED_BY_MODE else 'task'
        return ReadinessSnapshot(
            checks=self._checks,
            mode=normalized_mode,
            required=required_checks_for_mode(normalized_mode),
            controller_mode=self._controller_mode,
            runtime_phase=self._runtime_phase,
            task_stage=self._task_stage,
        )
