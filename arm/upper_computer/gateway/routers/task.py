from __future__ import annotations

from fastapi import APIRouter, Request

from ..api_common import request_id_from_request
from ..command_service import CommandExecutionPlan, GatewayCommandService
from ..errors import ApiException, ErrorCode, FailureClass
from ..lifespan import context_from_request
from ..models import new_correlation_id, new_request_id, wrap_response
from ..task_catalog import product_line_capabilities, public_task_templates, resolve_task_request, task_capability_summary
from ..schemas import StartTaskRequest, StartTaskResponseEnvelope
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


@router.post('/api/task/start', response_model=StartTaskResponseEnvelope)
async def post_task_start(body: StartTaskRequest, request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    command = GatewayCommandService(request, ctx=ctx)
    command_payload = body.model_dump()
    readiness = ctx.state.get_readiness()
    policy = validate_start_task(readiness, command.role)
    if not policy.allowed:
        command_policy = readiness.get('commandPolicies', {}).get('startTask', {})
        reason = str(policy.reason or '')
        task_execution_state = readiness.get('taskExecutionState', {}) if isinstance(readiness.get('taskExecutionState'), dict) else {}
        is_readiness_block = (
            (not readiness.get('allReady', False))
            or ('missing readiness' in reason)
            or (reason == readiness_stale_reason())
            or (command_policy.get('allowed') is False)
            or (
                bool(task_execution_state)
                and not str(reason or '').startswith('requires role')
                and (
                    not bool(task_execution_state.get('workbenchVisible', False))
                    or not bool(task_execution_state.get('interactive', False))
                    or not bool(task_execution_state.get('startAllowed', False))
                )
            )
        )
        command.require_policy(
            action='task.start',
            policy=policy,
            payload=command_payload,
            status_code=409 if is_readiness_block else 403,
            error=ErrorCode.READINESS_BLOCKED if is_readiness_block else ErrorCode.FORBIDDEN,
            failure_class=FailureClass.READINESS_BLOCKED if is_readiness_block else FailureClass.OPERATOR_BLOCKED,
            command_plane='task_control',
        )
    try:
        resolved = resolve_task_request(template_id=body.templateId, task_type=body.taskType, target_category=body.targetCategory)
    except ValueError as exc:
        command.require_policy(
            action='task.start',
            policy=PolicyResult(False, str(exc)),
            payload=body.model_dump(),
            status_code=422,
            error=ErrorCode.VALIDATION_ERROR,
            failure_class=FailureClass.CONTRACT_VIOLATION,
            command_plane='task_control',
        )
    runtime_tier = str(readiness.get('runtimeTier', 'preview') or 'preview')
    product_lines = product_line_capabilities()
    current_product_line = product_lines.get(runtime_tier, {})
    runtime_tier_order = {'preview': 0, 'validated_sim': 1, 'validated_live': 2}
    if runtime_tier_order.get(runtime_tier, 0) < runtime_tier_order.get(resolved.required_runtime_tier, 0):
        command.require_policy(
            action='task.start',
            policy=PolicyResult(False, f'template {resolved.template_id} requires runtime tier {resolved.required_runtime_tier}, current tier is {runtime_tier}'),
            payload=body.model_dump(),
            status_code=409,
            error=ErrorCode.READINESS_BLOCKED,
            failure_class=FailureClass.READINESS_BLOCKED,
            command_plane='task_control',
        )
    frontend_task_type = resolved.frontend_task_type
    target_category = resolved.target_category
    place_profile = resolved.place_profile
    correlation_id = new_correlation_id()
    task_run_id = new_request_id('taskrun')
    episode_id = new_request_id('episode')
    command_payload = {
        'task_type': resolved.backend_task_type,
        'target_selector': str(target_category or ''),
        'place_profile': place_profile,
        'auto_retry': True,
        'max_retry': 2,
        'request_id': request_id,
        'correlation_id': correlation_id,
        'task_run_id': task_run_id,
        'episode_id': episode_id,
        'template_id': resolved.template_id,
        'graph_key': resolved.graph_key,
        'plugin_key': resolved.plugin_key,
        'runtime_tier': runtime_tier,
    }

    def mutate_task_state(effective_ctx, transport_result):
        current = effective_ctx.state.start_task(transport_result['task_id'], frontend_task_type, target_category, request_id=request_id, correlation_id=correlation_id, task_run_id=task_run_id, episode_id=episode_id, template_id=resolved.template_id, place_profile=place_profile, runtime_tier=runtime_tier, graph_key=resolved.graph_key)
        return [('task.progress.updated', current)]

    async def invoke_start_task_transport():
        result = await ctx.ros.dispatch_runtime_command(command_plane='task_control', action='task.start', payload=command_payload)
        if not result.get('accepted'):
            command.require_policy(
                action='task.start',
                policy=PolicyResult(False, str(result.get('message', 'Task rejected'))),
                payload=body.model_dump(),
                status_code=409,
                error=ErrorCode.READINESS_BLOCKED,
                failure_class=FailureClass.READINESS_BLOCKED,
                command_plane='task_control',
            )
        return result

    result = await command.execute(
        CommandExecutionPlan(
            action='task.start',
            payload=command_payload,
            log_module='gateway.task',
            success_message=lambda transport_result: str(transport_result.get('message', 'task accepted')), 
            runtime_topics=('system', 'task'),
            command_plane='task_control',
            state_mutator=mutate_task_state,
        ),
        invoke_start_task_transport,
    )
    task_summary = task_capability_summary()
    resolved_template = next((item for item in task_summary.get('templates', []) if item.get('id') == resolved.template_id), {})
    return wrap_response({
        'taskId': result['task_id'],
        'taskRunId': task_run_id,
        'episodeId': episode_id,
        'templateId': resolved.template_id,
        'pluginKey': resolved.plugin_key,
        'graphKey': resolved.graph_key,
        'runtimeTier': runtime_tier,
        'productLine': current_product_line.get('label', runtime_tier),
        'catalogSchemaVersion': int(task_summary.get('schemaVersion', 2) or 2),
        'templateVersion': int(resolved_template.get('templateVersion', 1) or 1),
        'pluginContractVersion': int(resolved_template.get('pluginContractVersion', 1) or 1),
        'success': bool(result.get('success', False)) if bool(result.get('completionPending', True)) else bool(result.get('success', result.get('accepted', True))),
        'accepted': bool(result.get('accepted', True)),
        'authoritativeStatus': str(result.get('authoritativeStatus', 'accepted')),
        'completionPending': bool(result.get('completionPending', True)),
        'localPreviewOnly': bool(result.get('localPreviewOnly', False)),
        'message': str(result.get('message', 'task accepted')),
        'operationId': str(result.get('operationId', request_id)),
        'requestId': str(result.get('requestId', request_id)),
        'receiptId': str(result.get('receiptId', '')),
        'correlationId': correlation_id,
    }, request_id, correlation_id)


@router.post('/api/task/stop')
async def post_task_stop(request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    command = GatewayCommandService(request, ctx=ctx)
    result = await command.execute(
        CommandExecutionPlan(
            action='task.stop',
            log_level='warn',
            log_module='gateway.task',
            runtime_topics=('system', 'task', 'hardware'),
            command_plane='task_control',
        ),
        lambda: ctx.ros.dispatch_runtime_command(command_plane='task_control', action='task.stop', payload=None),
    )
    return wrap_response(result, request_id)
