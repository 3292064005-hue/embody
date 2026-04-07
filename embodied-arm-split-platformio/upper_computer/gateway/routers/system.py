from __future__ import annotations

from fastapi import APIRouter, Request

from ..api_common import request_id_from_request
from ..command_service import CommandExecutionPlan, GatewayCommandService
from ..lifespan import context_from_request
from ..models import coerce_system_state_aliases, wrap_response
from ..schemas import SetModeRequest

router = APIRouter()


@router.get('/api/system/summary')
async def get_system_summary(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_system(), request_id_from_request(request))


@router.get('/api/system/readiness')
async def get_system_readiness(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_readiness(), request_id_from_request(request))


@router.post('/api/system/home')
async def post_system_home(request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    command = GatewayCommandService(request, ctx=ctx)
    await command.execute(
        CommandExecutionPlan(
            action='system.home',
            required_role='operator',
            log_module='gateway.system',
            runtime_topics=('system', 'hardware'),
        ),
        ctx.ros.home,
    )
    return wrap_response(None, request_id)


@router.post('/api/system/reset-fault')
async def post_reset_fault(request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    command = GatewayCommandService(request, ctx=ctx)
    await command.execute(
        CommandExecutionPlan(
            action='system.reset_fault',
            required_role='operator',
            log_module='gateway.system',
            runtime_topics=('system', 'hardware'),
        ),
        ctx.ros.reset_fault,
    )
    return wrap_response(None, request_id)


@router.post('/api/system/recover')
async def post_recover(request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    command = GatewayCommandService(request, ctx=ctx)
    await command.execute(
        CommandExecutionPlan(
            action='system.recover',
            required_role='operator',
            log_module='gateway.system',
            runtime_topics=('system', 'hardware'),
        ),
        ctx.ros.recover,
    )
    return wrap_response(None, request_id)


@router.post('/api/system/emergency-stop')
async def post_estop(request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    command = GatewayCommandService(request, ctx=ctx)

    def mutate_estop_state(effective_ctx, result):
        system = effective_ctx.state.get_system()
        system['runtimePhase'] = 'safe_stop'
        system['controllerMode'] = 'maintenance'
        system['taskStage'] = 'failed'
        system['emergencyStop'] = True
        system['faultCode'] = 'ESTOP'
        system['faultMessage'] = result['message']
        effective_ctx.state.set_system(coerce_system_state_aliases(system))
        return None

    await command.execute(
        CommandExecutionPlan(
            action='system.emergency_stop',
            required_role='operator',
            log_level='fault',
            log_module='gateway.system',
            runtime_topics=('system', 'hardware'),
            state_mutator=mutate_estop_state,
        ),
        ctx.ros.emergency_stop,
    )
    return wrap_response(None, request_id)


@router.post('/api/hardware/set-mode')
async def post_set_mode(body: SetModeRequest, request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)

    def mutate_mode(effective_ctx, _result):
        effective_ctx.state.set_controller_mode(body.mode)
        return None

    command = GatewayCommandService(request, ctx=ctx)
    await command.execute(
        CommandExecutionPlan(
            action='hardware.set_mode',
            payload=body.model_dump(),
            required_role='operator' if body.mode in {'idle', 'task'} else 'maintainer',
            log_module='gateway.system',
            success_message='mode updated',
            runtime_topics=('system',),
            state_mutator=mutate_mode,
        ),
        lambda: ctx.ros.set_mode(mode=body.mode),
    )
    return wrap_response(None, request_id)
