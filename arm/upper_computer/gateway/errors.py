from __future__ import annotations

from enum import StrEnum
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from .models import now_iso, new_request_id


class ErrorCode(StrEnum):
    """Stable public error identifiers exposed by the gateway."""

    FORBIDDEN = 'forbidden'
    READINESS_BLOCKED = 'readiness_blocked'
    VALIDATION_ERROR = 'validation_error'
    NOT_IMPLEMENTED = 'not_implemented'
    NOT_FOUND = 'not_found'
    INTERNAL_ERROR = 'internal_error'


class FailureClass(StrEnum):
    """Internal-facing failure taxonomy used for logs, audits, and error envelopes."""

    OPERATOR_BLOCKED = 'operator_blocked'
    READINESS_BLOCKED = 'readiness_blocked'
    CONTRACT_VIOLATION = 'contract_violation'
    DEPENDENCY_UNAVAILABLE = 'dependency_unavailable'
    TRANSIENT_IO_FAILURE = 'transient_io_failure'
    INTERNAL_BUG = 'internal_bug'


class GatewayCommandError(Exception):
    """Structured gateway command failure."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        error: ErrorCode,
        failure_class: FailureClass,
        code: int | None = None,
        operator_actionable: bool = True,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.error = error
        self.failure_class = failure_class
        self.code = code or status_code
        self.operator_actionable = operator_actionable

    def to_api_exception(self) -> 'ApiException':
        return ApiException(
            self.status_code,
            self.message,
            code=self.code,
            error=self.error,
            failure_class=self.failure_class,
            operator_actionable=self.operator_actionable,
        )


class ApiException(HTTPException):
    """Gateway exception carrying both HTTP and stable public error codes."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        code: int | None = None,
        error: ErrorCode | None = None,
        failure_class: FailureClass | None = None,
        operator_actionable: bool | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.error_code = code or status_code
        self.error = error or _default_error(status_code)
        self.failure_class = failure_class or _default_failure_class(status_code)
        self.operator_actionable = operator_actionable


def _default_error(status_code: int) -> ErrorCode:
    if status_code == 403:
        return ErrorCode.FORBIDDEN
    if status_code == 404:
        return ErrorCode.NOT_FOUND
    if status_code == 409:
        return ErrorCode.READINESS_BLOCKED
    if status_code == 422:
        return ErrorCode.VALIDATION_ERROR
    if status_code == 501:
        return ErrorCode.NOT_IMPLEMENTED
    return ErrorCode.INTERNAL_ERROR


def _default_failure_class(status_code: int) -> FailureClass:
    if status_code == 403:
        return FailureClass.OPERATOR_BLOCKED
    if status_code == 409:
        return FailureClass.READINESS_BLOCKED
    if status_code == 422:
        return FailureClass.CONTRACT_VIOLATION
    if status_code in {502, 503}:
        return FailureClass.DEPENDENCY_UNAVAILABLE
    if status_code == 504:
        return FailureClass.TRANSIENT_IO_FAILURE
    return FailureClass.INTERNAL_BUG


def error_response(
    status_code: int,
    message: str,
    request_id: str | None = None,
    *,
    code: int | None = None,
    error: ErrorCode | None = None,
    failure_class: FailureClass | None = None,
    operator_actionable: bool | None = None,
):
    """Build a stable JSON error envelope."""
    resolved_error = error or _default_error(status_code)
    resolved_failure_class = failure_class or _default_failure_class(status_code)
    return JSONResponse(
        status_code=status_code,
        content={
            'code': code or status_code,
            'error': str(resolved_error),
            'failureClass': str(resolved_failure_class),
            'message': message,
            'requestId': request_id or new_request_id(),
            'timestamp': now_iso(),
            'detail': message,
            'operatorActionable': operator_actionable,
        },
    )
