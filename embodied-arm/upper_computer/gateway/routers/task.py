from __future__ import annotations

from fastapi import APIRouter, Request

from ..api_common import request_id_from_request
from ..command_service import CommandExecutionPlan, GatewayCommandService
from ..errors import ApiException, ErrorCode, FailureClass
from ..lifespan import context_from_request
from ..models import new_correlation_id, new_request_id, wrap_response
from ..task_catalog import product_line_capabilities, public_task_templates, resolve_task_request
from ..schemas import StartTaskRequest
from ..readiness_snapshot import readiness_stale_reason
from ..security import PolicyResult, validate_start_task

router = APIRouter()


@router.get('/api/task/current')
async def get_task_current(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_current_task(), request_id_from_request(request))


@router.get('/api/task/templates')
async def get_task_templates(request: Request):
    return wrap_response(public_task_templates(), request_id_from_request(request))


@router.get('/api/task/history')
async def get_task_history(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_task_history(), request_id_from_request(request))


@router.post('/api/task/start')
async def post_task_start(body: StartTaskRequest, request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    command = GatewayCommandService(request, ctx=ctx)
    readiness = ctx.state.get_readiness()
    policy = validate_start_task(readiness, command.role)
    if not policy.allowed:
        command_policy = readiness.get('commandPolicies', {}).get('startTask', {})
        reason = str(policy.reason or '')
        is_readiness_block = (
            (not readiness.get('allReady', False))
            or ('missing readiness' in reason)
            or (reason == readiness_stale_reason())
            or (command_policy.get('allowed') is False)
        )
        command.require_policy(
            action='task.start',
            policy=policy,
            payload=body.model_dump(),
            status_code=409 if is_readiness_block else 403,
            error=ErrorCode.READINESS_BLOCKED if is_readiness_block else ErrorCode.FORBIDDEN,
            failure_class=FailureClass.READINESS_BLOCKED if is_readiness_block else FailureClass.OPERATOR_BLOCKED,
        )
    try:
        resolved = resolve_task_request(template_id=body.templateId, task_type=body.taskType, target_category=body.targetCategory)
    except ValueError as exc:
        raise ApiException(422, str(exc), error=ErrorCode.VALIDATION_ERROR, failure_class=FailureClass.CONTRACT_VIOLATION)
    runtime_tier = str(readiness.get('runtimeTier', 'preview') or 'preview')
    product_lines = product_line_capabilities()
    current_product_line = product_lines.get(runtime_tier, {})
    runtime_tier_order = {'preview': 0, 'validated_sim': 1, 'validated_live': 2}
    if runtime_tier_order.get(runtime_tier, 0) < runtime_tier_order.get(resolved.required_runtime_tier, 0):
        raise ApiException(
            409,
            f'template {resolved.template_id} requires runtime tier {resolved.required_runtime_tier}, current tier is {runtime_tier}',
            error=ErrorCode.READINESS_BLOCKED,
            failure_class=FailureClass.READINESS_BLOCKED,
        )
    frontend_task_type = resolved.frontend_task_type
    target_category = resolved.target_category
    place_profile = resolved.place_profile
    result = await ctx.ros.start_task(task_type=resolved.backend_task_type, target_selector=str(target_category or ''), place_profile=place_profile, auto_retry=True, max_retry=2)
    if not result.get('accepted'):
        command.require_policy(
            action='task.start',
            policy=PolicyResult(False, str(result.get('message', 'Task rejected'))),
            payload=body.model_dump(),
            status_code=409,
            error=ErrorCode.READINESS_BLOCKED,
            failure_class=FailureClass.READINESS_BLOCKED,
        )
    correlation_id = new_correlation_id()
    task_run_id = new_request_id('taskrun')

    def mutate_task_state(effective_ctx, transport_result):
        current = effective_ctx.state.start_task(transport_result['task_id'], frontend_task_type, target_category, request_id=request_id, correlation_id=correlation_id, task_run_id=task_run_id, template_id=resolved.template_id, place_profile=place_profile, runtime_tier=runtime_tier)
        return [('task.progress.updated', current)]

    async def return_transport_result():
        return result

    await command.execute(
        CommandExecutionPlan(
            action='task.start',
            payload=body.model_dump(),
            log_module='gateway.task',
            success_message=result.get('message', 'task accepted'),
            runtime_topics=('system', 'task'),
            state_mutator=mutate_task_state,
        ),
        return_transport_result,
    )
    return wrap_response({'taskId': result['task_id'], 'taskRunId': task_run_id, 'templateId': resolved.template_id, 'runtimeTier': runtime_tier, 'productLine': current_product_line.get('label', runtime_tier)}, request_id, correlation_id)


@router.post('/api/task/stop')
async def post_task_stop(request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    command = GatewayCommandService(request, ctx=ctx)
    await command.execute(
        CommandExecutionPlan(
            action='task.stop',
            required_role='operator',
            log_level='warn',
            log_module='gateway.task',
            runtime_topics=('system', 'task', 'hardware'),
        ),
        ctx.ros.stop_task,
    )
    return wrap_response(None, request_id)
