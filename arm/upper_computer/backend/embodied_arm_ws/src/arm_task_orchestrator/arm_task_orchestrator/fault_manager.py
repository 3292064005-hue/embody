from __future__ import annotations

from dataclasses import dataclass

from arm_backend_common.enums import FaultCode


@dataclass(frozen=True)
class FaultDecision:
    action: str
    fault: FaultCode
    terminal: bool
    reason: str


class FaultManager:
    """Centralized task fault classification and terminal-state mapping."""

    RETRYABLE = {
        FaultCode.TARGET_NOT_FOUND,
        FaultCode.TARGET_STALE,
        FaultCode.VISION_TIMEOUT,
        FaultCode.PLAN_FAILED,
        FaultCode.EXECUTE_TIMEOUT,
    }

    def classify(self, fault: FaultCode, reason: str) -> FaultDecision:
        """Classify a fault into retryable or terminal handling."""
        if fault in self.RETRYABLE:
            return FaultDecision(action='retry_or_fault', fault=fault, terminal=False, reason=reason)
        return FaultDecision(action='fault', fault=fault, terminal=True, reason=reason)
