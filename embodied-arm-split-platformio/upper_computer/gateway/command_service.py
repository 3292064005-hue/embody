from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

from fastapi import Request

from .api_common import append_audit, append_log, request_id_from_request, role_from_request
from .errors import ErrorCode, FailureClass, GatewayCommandError
from .lifespan import AppContext, context_from_request
from .ros_bridge import RosBridgeError
from .runtime_projection import ProjectionTopic
from .security import PolicyResult, require_role

StateMutator = Callable[[AppContext, dict[str, Any]], Iterable[tuple[str, Any]] | None]
AsyncCommand = Callable[[], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class CommandExecutionPlan:
    action: str
    payload: dict[str, Any] | None = None
    required_role: str | None = None
    blocked_status_code: int = 403
    blocked_error: ErrorCode = ErrorCode.FORBIDDEN
    blocked_failure_class: FailureClass = FailureClass.OPERATOR_BLOCKED
    log_level: str = 'info'
    log_module: str = 'gateway.command'
    log_event: str | None = None
    success_message: str | Callable[[dict[str, Any]], str] | None = None
    runtime_topics: tuple[ProjectionTopic, ...] = field(default_factory=tuple)
    state_mutator: StateMutator | None = None
    extra_events: tuple[tuple[str, Any], ...] = field(default_factory=tuple)
    operator_actionable: bool = True


class GatewayCommandService:
    """Execute gateway command flows with a single, testable pipeline."""

    def __init__(self, request: Request, *, ctx: AppContext | None = None) -> None:
        """Bind a request-scoped command executor to the active application context.

        Args:
            request: FastAPI request used to resolve request id, caller role, and app state.
            ctx: Optional pre-resolved application context for tests or internal reuse.

        Returns:
            None.

        Raises:
            No explicit exception is raised here; downstream request parsing failures bubble up.

        Boundary behavior:
            When `ctx` is omitted, the function resolves the context from the request object.
        """
        self.ctx = ctx or context_from_request(request)
        self.request_id = request_id_from_request(request)
        self.role = role_from_request(request)

    def require_role(self, plan: CommandExecutionPlan) -> None:
        """Enforce the minimum caller role declared by a command plan.

        Args:
            plan: Command execution metadata describing the required role and block policy.

        Returns:
            None.

        Raises:
            ApiException: Raised when the active caller role does not satisfy the plan.

        Boundary behavior:
            Returns immediately when the plan does not declare a required role.
        """
        if not plan.required_role:
            return
        policy = require_role(self.role, plan.required_role)
        self.require_policy(
            action=plan.action,
            policy=policy,
            payload=plan.payload,
            status_code=plan.blocked_status_code,
            error=plan.blocked_error,
            failure_class=plan.blocked_failure_class,
            operator_actionable=plan.operator_actionable,
        )

    def require_policy(
        self,
        *,
        action: str,
        policy: PolicyResult,
        payload: dict[str, Any] | None = None,
        status_code: int,
        error: ErrorCode,
        failure_class: FailureClass,
        operator_actionable: bool = True,
    ) -> None:
        """Apply a precomputed readiness or validation policy to the current command.

        Args:
            action: Stable command action name used for audit logging.
            policy: Policy evaluation result from gateway security helpers.
            payload: Optional request payload echoed into blocked audits.
            status_code: HTTP status code returned when the policy blocks the command.
            error: Stable public error code exposed to clients.
            failure_class: Internal failure taxonomy emitted to logs and responses.
            operator_actionable: Whether the resulting error should be shown as operator-fixable.

        Returns:
            None.

        Raises:
            ApiException: Raised when `policy.allowed` is false.

        Boundary behavior:
            Successful policies are a no-op and do not emit audit events.
        """
        if policy.allowed:
            return
        append_audit(
            action,
            'blocked',
            self.request_id,
            self.role,
            message=policy.reason,
            payload=payload,
            error_code=str(failure_class),
            operator_actionable=operator_actionable,
            ctx=self.ctx,
        )
        raise GatewayCommandError(
            status_code,
            policy.reason,
            error=error,
            failure_class=failure_class,
            operator_actionable=operator_actionable,
        ).to_api_exception()


    async def _publish_failure(self, plan: CommandExecutionPlan, exc: GatewayCommandError) -> None:
        """Emit structured log and audit records for a failed command execution.

        Args:
            plan: Command metadata describing the action and payload being executed.
            exc: Structured command failure that should be surfaced to clients.

        Returns:
            None. Side effects are best-effort and intentionally do not mask the original failure.

        Raises:
            Does not raise. Downstream logging or websocket publication failures are suppressed.

        Boundary behavior:
            Failure publication uses the command action and request metadata even when the transport
            never returned a result, so operator-visible diagnostics remain correlated to the request.
        """
        try:
            log = append_log(
                'error',
                plan.log_module,
                f"{plan.log_event or plan.action}.failed",
                exc.message,
                request_id=self.request_id,
                payload=plan.payload,
                error_code=str(exc.error),
                operator_actionable=exc.operator_actionable,
                ctx=self.ctx,
            )
            audit = append_audit(
                plan.action,
                'failed',
                self.request_id,
                self.role,
                message=exc.message,
                payload=plan.payload,
                error_code=str(exc.error),
                operator_actionable=exc.operator_actionable,
                ctx=self.ctx,
            )
            await self.ctx.ws.publish('log.event.created', log)
            await self.ctx.ws.publish('audit.event.created', audit)
        except Exception:
            return

    def _map_transport_failure(self, exc: Exception) -> GatewayCommandError:
        """Translate transport and dependency failures into stable gateway error semantics.

        Args:
            exc: Raw exception raised by the transport or dependency layer.

        Returns:
            A structured ``GatewayCommandError`` describing the stable HTTP/error taxonomy.

        Raises:
            No exception is raised directly; callers receive the returned structured error.

        Boundary behavior:
            Timeouts become transient I/O failures (504), while dependency and ROS bridge
            availability failures become dependency-unavailable responses (503). Unknown
            exceptions are treated as internal bugs and must be surfaced by the generic handler.
        """
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            return GatewayCommandError(
                504,
                'command transport timeout',
                error=ErrorCode.INTERNAL_ERROR,
                failure_class=FailureClass.TRANSIENT_IO_FAILURE,
                operator_actionable=False,
            )
        if isinstance(exc, RosBridgeError):
            message = str(exc) or 'ROS bridge failure'
            lowered = message.lower()
            if 'timeout' in lowered:
                return GatewayCommandError(
                    504,
                    message,
                    error=ErrorCode.INTERNAL_ERROR,
                    failure_class=FailureClass.TRANSIENT_IO_FAILURE,
                    operator_actionable=False,
                )
            return GatewayCommandError(
                503,
                message,
                error=ErrorCode.INTERNAL_ERROR,
                failure_class=FailureClass.DEPENDENCY_UNAVAILABLE,
                operator_actionable=False,
            )
        if isinstance(exc, (ConnectionError, OSError)):
            return GatewayCommandError(
                503,
                'dependent transport unavailable',
                error=ErrorCode.INTERNAL_ERROR,
                failure_class=FailureClass.DEPENDENCY_UNAVAILABLE,
                operator_actionable=False,
            )
        return GatewayCommandError(
            500,
            'internal server error',
            error=ErrorCode.INTERNAL_ERROR,
            failure_class=FailureClass.INTERNAL_BUG,
            operator_actionable=False,
        )

    async def execute(self, plan: CommandExecutionPlan, invoke: AsyncCommand) -> dict[str, Any]:
        """Run a gateway command end-to-end, including audit, log, and projection updates.

        Args:
            plan: Declarative command metadata describing roles, runtime topics, and side effects.
            invoke: Awaitable transport callback that performs the underlying ROS or service action.

        Returns:
            The transport result dictionary returned by `invoke`.

        Raises:
            ApiException: Raised when role checks, policy checks, or structured command failures occur.

        Boundary behavior:
            State mutation hooks run only after the transport call succeeds, and readiness/diagnostics
            projections are always republished alongside the plan-declared runtime topics.
        """
        try:
            self.require_role(plan)
            result = await invoke()
        except GatewayCommandError as exc:
            if exc.status_code >= 500:
                await self._publish_failure(plan, exc)
            raise exc.to_api_exception() from exc
        except Exception as exc:
            mapped = self._map_transport_failure(exc)
            await self._publish_failure(plan, mapped)
            raise mapped.to_api_exception() from exc
        extra_events = list(plan.extra_events)
        if plan.state_mutator is not None:
            extra_from_state = plan.state_mutator(self.ctx, result)
            if extra_from_state:
                extra_events.extend(extra_from_state)
        message = plan.success_message(result) if callable(plan.success_message) else (plan.success_message or result.get('message', 'ok'))
        log = append_log(
            plan.log_level,
            plan.log_module,
            plan.log_event or plan.action,
            message,
            request_id=self.request_id,
            payload=plan.payload,
            ctx=self.ctx,
        )
        audit = append_audit(
            plan.action,
            'success',
            self.request_id,
            self.role,
            message=message,
            payload=plan.payload,
            ctx=self.ctx,
        )
        await self.ctx.ws.publish('log.event.created', log)
        await self.ctx.ws.publish('audit.event.created', audit)
        publish_topics: tuple[ProjectionTopic, ...] = (*plan.runtime_topics, 'readiness', 'diagnostics')
        await self.ctx.events.publish_topics(*publish_topics, extra_events=extra_events)
        return result
