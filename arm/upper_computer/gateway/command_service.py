from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Literal

from fastapi import Request

from .api_common import append_audit, append_command_receipt, append_log, request_id_from_request, role_from_request
from .command_contracts import execution_bound_for_command_plane, minimum_role_for_command_plane, receipt_class_for_command_plane, runtime_interface_active, runtime_interface_for_command_plane
from .errors import ApiException, ErrorCode, FailureClass, GatewayCommandError
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
    command_plane: str = 'system_control'
    receipt_class: str | None = None
    execution_bound: bool | None = None
    runtime_interface: str | None = None
    success_status: Literal['accepted', 'success'] = 'accepted'


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


    def _resolved_plan(self, plan: CommandExecutionPlan) -> CommandExecutionPlan:
        """Return one command plan with contract-derived defaults resolved.

        Args:
            plan: Raw command execution plan declared by a router or service.

        Returns:
            CommandExecutionPlan: Effective plan with role, receipt class, and
            execution binding normalized from the authoritative command-plane
            contract when the caller does not override them explicitly.

        Raises:
            Does not raise. Unknown command planes are allowed to bubble from the
            contract helper so tests fail loudly.
        """
        required_role = plan.required_role
        if required_role is None:
            required_role = minimum_role_for_command_plane(plan.command_plane)
        receipt_class = plan.receipt_class or receipt_class_for_command_plane(plan.command_plane)
        execution_bound = plan.execution_bound if plan.execution_bound is not None else execution_bound_for_command_plane(plan.command_plane)
        runtime_interface = plan.runtime_interface or runtime_interface_for_command_plane(plan.command_plane)
        if required_role == plan.required_role and receipt_class == plan.receipt_class and execution_bound == plan.execution_bound and runtime_interface == plan.runtime_interface:
            return plan
        return CommandExecutionPlan(
            action=plan.action,
            payload=plan.payload,
            required_role=required_role,
            blocked_status_code=plan.blocked_status_code,
            blocked_error=plan.blocked_error,
            blocked_failure_class=plan.blocked_failure_class,
            log_level=plan.log_level,
            log_module=plan.log_module,
            log_event=plan.log_event,
            success_message=plan.success_message,
            runtime_topics=plan.runtime_topics,
            state_mutator=plan.state_mutator,
            extra_events=plan.extra_events,
            operator_actionable=plan.operator_actionable,
            command_plane=plan.command_plane,
            receipt_class=receipt_class,
            execution_bound=execution_bound,
            runtime_interface=runtime_interface,
            success_status=plan.success_status,
        )

    def _schedule_event_publish(self, event: str, payload: dict[str, Any]) -> None:
        """Publish one websocket event on the current loop when available.

        This helper is used by synchronous policy guards so blocked receipts and
        audits still reach websocket subscribers without requiring async call sites.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.ctx.ws.publish(event, payload))


    @staticmethod
    def _payload_trace_ids(payload: dict[str, Any] | None) -> dict[str, str]:
        if not isinstance(payload, dict):
            return {'task_run_id': '', 'episode_id': '', 'correlation_id': '', 'task_id': ''}
        return {
            'task_run_id': str(payload.get('task_run_id', payload.get('taskRunId', '')) or ''),
            'episode_id': str(payload.get('episode_id', payload.get('episodeId', '')) or ''),
            'correlation_id': str(payload.get('correlation_id', payload.get('correlationId', '')) or ''),
            'task_id': str(payload.get('task_id', payload.get('taskId', '')) or ''),
        }

    def require_runtime_interface(self, plan: CommandExecutionPlan) -> None:
        """Enforce that the runtime interface bound to one command plan is active.

        Args:
            plan: Command execution metadata describing the runtime interface.

        Returns:
            None.

        Raises:
            ApiException: Raised when the bound runtime interface is not active.

        Boundary behavior:
            Observability and command planes share the same gate semantics: if
            the authoritative registry marks the runtime interface as reserved,
            experimental, or deprecated, the gateway fails closed before
            transport dispatch and emits a blocked receipt.
        """
        effective_plan = self._resolved_plan(plan)
        runtime_interface = str(effective_plan.runtime_interface or '')
        if not runtime_interface:
            return
        if runtime_interface_active(runtime_interface):
            return
        self.require_policy(
            action=effective_plan.action,
            policy=PolicyResult(False, f'runtime interface {runtime_interface} is not active'),
            payload=effective_plan.payload,
            status_code=422,
            error=ErrorCode.VALIDATION_ERROR,
            failure_class=FailureClass.CONTRACT_VIOLATION,
            operator_actionable=False,
            command_plane=effective_plan.command_plane,
            receipt_class=effective_plan.receipt_class,
            execution_bound=bool(effective_plan.execution_bound),
        )

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
        effective_plan = self._resolved_plan(plan)
        if not effective_plan.required_role:
            return
        policy = require_role(self.role, effective_plan.required_role)
        self.require_policy(
            action=effective_plan.action,
            policy=policy,
            payload=plan.payload,
            status_code=effective_plan.blocked_status_code,
            error=effective_plan.blocked_error,
            failure_class=effective_plan.blocked_failure_class,
            operator_actionable=effective_plan.operator_actionable,
            command_plane=effective_plan.command_plane,
            receipt_class=effective_plan.receipt_class,
            execution_bound=bool(effective_plan.execution_bound),
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
        command_plane: str = 'system_control',
        receipt_class: str | None = None,
        execution_bound: bool | None = None,
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
        effective_receipt_class = receipt_class or receipt_class_for_command_plane(command_plane)
        effective_execution_bound = execution_bound if execution_bound is not None else execution_bound_for_command_plane(command_plane)
        trace_ids = self._payload_trace_ids(payload)
        audit = append_audit(
            action,
            'blocked',
            self.request_id,
            self.role,
            message=policy.reason,
            payload=payload,
            correlation_id=trace_ids['correlation_id'] or None,
            task_id=trace_ids['task_id'] or None,
            task_run_id=trace_ids['task_run_id'] or None,
            episode_id=trace_ids['episode_id'] or None,
            error_code=str(failure_class),
            operator_actionable=operator_actionable,
            ctx=self.ctx,
        )
        receipt = append_command_receipt(
            action,
            'blocked',
            self.request_id,
            self.role,
            command_plane=command_plane,
            receipt_class=effective_receipt_class,
            execution_bound=bool(effective_execution_bound),
            message=policy.reason,
            payload=payload,
            correlation_id=trace_ids['correlation_id'] or None,
            task_run_id=trace_ids['task_run_id'] or None,
            episode_id=trace_ids['episode_id'] or None,
            error_code=str(failure_class),
            operator_actionable=operator_actionable,
            ctx=self.ctx,
        )
        self._schedule_event_publish('audit.event.created', audit)
        self._schedule_event_publish('command.receipt.created', receipt)
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
        effective_plan = self._resolved_plan(plan)
        try:
            trace_ids = self._payload_trace_ids(plan.payload)
            log = append_log(
                'error',
                effective_plan.log_module,
                f"{effective_plan.log_event or effective_plan.action}.failed",
                exc.message,
                request_id=self.request_id,
                correlation_id=trace_ids['correlation_id'] or None,
                task_id=trace_ids['task_id'] or None,
                task_run_id=trace_ids['task_run_id'] or None,
                episode_id=trace_ids['episode_id'] or None,
                payload=plan.payload,
                error_code=str(exc.error),
                operator_actionable=exc.operator_actionable,
                ctx=self.ctx,
            )
            audit = append_audit(
                effective_plan.action,
                'failed',
                self.request_id,
                self.role,
                message=exc.message,
                payload=plan.payload,
                correlation_id=trace_ids['correlation_id'] or None,
                task_id=trace_ids['task_id'] or None,
                task_run_id=trace_ids['task_run_id'] or None,
                episode_id=trace_ids['episode_id'] or None,
                error_code=str(exc.error),
                operator_actionable=exc.operator_actionable,
                ctx=self.ctx,
            )
            receipt = append_command_receipt(
                effective_plan.action,
                'failed',
                self.request_id,
                self.role,
                command_plane=effective_plan.command_plane,
                receipt_class=effective_plan.receipt_class,
                execution_bound=bool(effective_plan.execution_bound),
                message=exc.message,
                payload=plan.payload,
                correlation_id=trace_ids['correlation_id'] or None,
                task_run_id=trace_ids['task_run_id'] or None,
                episode_id=trace_ids['episode_id'] or None,
                error_code=str(exc.error),
                operator_actionable=exc.operator_actionable,
                ctx=self.ctx,
            )
            await self.ctx.ws.publish('log.event.created', log)
            await self.ctx.ws.publish('audit.event.created', audit)
            await self.ctx.ws.publish('command.receipt.created', receipt)
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


    @staticmethod
    def _command_accepted(result: dict[str, Any]) -> bool:
        """Return whether one transport result represents an accepted command.

        The gateway fails closed when the transport explicitly reports ``accepted``
        or legacy ``success`` as false. Missing acceptance fields default to
        rejected so routers do not accidentally widen admission during schema
        migrations or transport bugs.
        existing transports can migrate incrementally.
        """
        if 'accepted' in result:
            return bool(result.get('accepted'))
        if 'success' in result:
            return bool(result.get('success'))
        return False

    def _normalize_success_result(
        self,
        effective_plan: CommandExecutionPlan,
        result: dict[str, Any],
        *,
        message: str,
        receipt_id: str,
    ) -> dict[str, Any]:
        """Attach public command-lifecycle metadata to one transport result.

        Args:
            effective_plan: Resolved command execution metadata.
            result: Transport payload returned by the runtime bridge.
            message: Operator-facing lifecycle summary emitted into audit/receipt/log.
            receipt_id: Persisted command-receipt identifier linked to this request.

        Returns:
            dict[str, Any]: Public command result carrying accepted/completion semantics.

        Boundary behavior:
            The public REST contract reports an initial acceptance state only. Even
            when a lower layer completed synchronously, callers must still consume
            authoritative state/receipt updates for completion truth.
        """
        normalized = dict(result)
        transport_message = str(normalized.get('message', '') or message)
        transport_accepted = self._command_accepted(normalized)
        normalized['message'] = str(message)
        normalized.setdefault('transportMessage', transport_message)
        completion_pending = effective_plan.success_status != 'success'
        normalized.setdefault('transportAccepted', transport_accepted)
        normalized.setdefault('accepted', transport_accepted)
        normalized.setdefault('success', transport_accepted and not completion_pending)
        normalized.setdefault('commandAccepted', transport_accepted)
        normalized.setdefault('authoritativeStatus', 'accepted' if completion_pending else 'success')
        normalized.setdefault('completionPending', completion_pending)
        normalized.setdefault('operationId', self.request_id)
        normalized.setdefault('requestId', self.request_id)
        normalized.setdefault('receiptId', receipt_id)
        return normalized

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
        effective_plan = self._resolved_plan(plan)
        try:
            self.require_runtime_interface(effective_plan)
            self.require_role(effective_plan)
            result = await invoke()
        except GatewayCommandError as exc:
            if exc.status_code >= 500:
                await self._publish_failure(effective_plan, exc)
            raise exc.to_api_exception() from exc
        except ApiException:
            raise
        except Exception as exc:
            mapped = self._map_transport_failure(exc)
            await self._publish_failure(effective_plan, mapped)
            raise mapped.to_api_exception() from exc
        normalized_result = dict(result)
        if not self._command_accepted(normalized_result):
            mapped = GatewayCommandError(
                409,
                str(normalized_result.get('message', 'runtime command rejected')),
                error=ErrorCode.READINESS_BLOCKED,
                failure_class=FailureClass.READINESS_BLOCKED,
                operator_actionable=True,
            )
            await self._publish_failure(effective_plan, mapped)
            raise mapped.to_api_exception()
        extra_events = list(effective_plan.extra_events)
        if effective_plan.state_mutator is not None:
            extra_from_state = effective_plan.state_mutator(self.ctx, normalized_result)
            if extra_from_state:
                extra_events.extend(extra_from_state)
        message = effective_plan.success_message(normalized_result) if callable(effective_plan.success_message) else (effective_plan.success_message or normalized_result.get('message', 'command accepted'))
        success_status = effective_plan.success_status
        trace_ids = self._payload_trace_ids(effective_plan.payload)
        log = append_log(
            effective_plan.log_level,
            effective_plan.log_module,
            effective_plan.log_event or effective_plan.action,
            message,
            request_id=self.request_id,
            correlation_id=trace_ids['correlation_id'] or None,
            task_id=trace_ids['task_id'] or None,
            task_run_id=trace_ids['task_run_id'] or None,
            episode_id=trace_ids['episode_id'] or None,
            payload=plan.payload,
            ctx=self.ctx,
        )
        audit = append_audit(
            effective_plan.action,
            success_status,
            self.request_id,
            self.role,
            message=message,
            payload=plan.payload,
            correlation_id=trace_ids['correlation_id'] or None,
            task_id=trace_ids['task_id'] or None,
            task_run_id=trace_ids['task_run_id'] or None,
            episode_id=trace_ids['episode_id'] or None,
            ctx=self.ctx,
        )
        receipt = append_command_receipt(
            effective_plan.action,
            success_status,
            self.request_id,
            self.role,
            command_plane=effective_plan.command_plane,
            receipt_class=effective_plan.receipt_class,
            execution_bound=bool(effective_plan.execution_bound),
            message=message,
            payload={**(effective_plan.payload or {}), **({'transportResult': normalized_result} if isinstance(normalized_result, dict) else {})},
            correlation_id=trace_ids['correlation_id'] or None,
            task_run_id=trace_ids['task_run_id'] or None,
            episode_id=trace_ids['episode_id'] or None,
            ctx=self.ctx,
        )
        public_result = self._normalize_success_result(effective_plan, normalized_result, message=message, receipt_id=str(receipt.get('id', '')))
        await self.ctx.ws.publish('log.event.created', log)
        await self.ctx.ws.publish('audit.event.created', audit)
        await self.ctx.ws.publish('command.receipt.created', receipt)
        publish_topics: tuple[ProjectionTopic, ...] = (*effective_plan.runtime_topics, 'readiness', 'diagnostics')
        await self.ctx.events.publish_topics(*publish_topics, extra_events=extra_events)
        return public_result
