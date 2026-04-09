from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Request

from ..api_common import request_id_from_request
from ..command_service import CommandExecutionPlan, GatewayCommandService
from ..errors import ErrorCode, FailureClass
from ..lifespan import context_from_request
from ..models import wrap_response
from ..schemas import GripperRequest, JogJointRequest, ServoCartesianRequest
from ..security import validate_gripper_command, validate_jog_command, validate_servo_command

router = APIRouter()


@router.get('/api/hardware/state')
async def get_hardware_state(request: Request):
    ctx = context_from_request(request)
    return wrap_response(ctx.state.get_hardware(), request_id_from_request(request))


@router.post('/api/hardware/gripper')
async def post_gripper(body: GripperRequest, request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    command = GatewayCommandService(request, ctx=ctx)
    plan = CommandExecutionPlan(
        action='hardware.gripper',
        payload=body.model_dump(),
        required_role='operator',
        log_module='gateway.hardware',
        success_message='gripper command sent',
        runtime_topics=('hardware',),
    )
    command.require_role(plan)
    controller_mode = ctx.state.get_system().get('controllerMode', ctx.state.get_system().get('operatorMode', 'idle'))
    command.require_policy(
        action=plan.action,
        policy=validate_gripper_command(controller_mode, ctx.state.get_readiness()),
        payload=plan.payload,
        status_code=409,
        error=ErrorCode.READINESS_BLOCKED,
        failure_class=FailureClass.READINESS_BLOCKED,
    )

    def mutate_gripper(effective_ctx, _result):
        effective_ctx.state.set_gripper_open(body.open)
        return None

    await command.execute(replace(plan, state_mutator=mutate_gripper), lambda: ctx.ros.command_gripper(open_gripper=body.open))
    return wrap_response(None, request_id)


@router.post('/api/hardware/jog-joint')
async def post_jog_joint(body: JogJointRequest, request: Request):
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    command = GatewayCommandService(request, ctx=ctx)
    plan = CommandExecutionPlan(
        action='hardware.jog_joint',
        payload=body.model_dump(),
        required_role='maintainer',
        log_level='warn',
        log_module='gateway.hardware',
        success_message='jog command sent',
        runtime_topics=('hardware',),
    )
    command.require_role(plan)
    controller_mode = ctx.state.get_system().get('controllerMode', ctx.state.get_system().get('operatorMode', 'idle'))
    command.require_policy(
        action=plan.action,
        policy=validate_jog_command(body.jointIndex, body.direction, body.stepDeg, controller_mode, ctx.state.get_readiness()),
        payload=plan.payload,
        status_code=409,
        error=ErrorCode.READINESS_BLOCKED,
        failure_class=FailureClass.READINESS_BLOCKED,
    )
    await command.execute(plan, lambda: ctx.ros.jog_joint(joint_index=body.jointIndex, direction=body.direction, step_deg=body.stepDeg))
    return wrap_response(None, request_id)


@router.post('/api/hardware/servo-cartesian')
async def post_servo_cartesian(body: ServoCartesianRequest, request: Request):
    """Dispatch a validated cartesian servo command to the ROS bridge.

    Args:
        body: Validated cartesian servo command payload.
        request: FastAPI request carrying the runtime app context and actor headers.

    Returns:
        A wrapped empty success response bound to the current request id.

    Raises:
        ApiException: Raised when role or readiness policy blocks the command.

    Boundary behavior:
        Returns HTTP 501 for intentionally disabled contract branches and HTTP 409
        for readiness-gated blocks without mutating gateway state.
    """
    ctx = context_from_request(request)
    request_id = request_id_from_request(request)
    CTX = ctx
    command = GatewayCommandService(request, ctx=ctx)
    plan = CommandExecutionPlan(
        action='hardware.servo_cartesian',
        payload=body.model_dump(),
        required_role='maintainer',
        log_level='warn',
        log_module='gateway.hardware',
        success_message='servo command sent',
        runtime_topics=('hardware',),
    )
    command.require_role(plan)
    controller_mode = ctx.state.get_system().get('controllerMode', ctx.state.get_system().get('operatorMode', 'idle'))
    policy = validate_servo_command(body.axis, body.delta, controller_mode, ctx.state.get_readiness())
    status_code = 501 if 'disabled' in policy.reason else 409
    command.require_policy(
        action=plan.action,
        policy=policy,
        payload=plan.payload,
        status_code=status_code,
        error=ErrorCode.NOT_IMPLEMENTED if status_code == 501 else ErrorCode.READINESS_BLOCKED,
        failure_class=FailureClass.CONTRACT_VIOLATION if status_code == 501 else FailureClass.READINESS_BLOCKED,
    )

    async def invoke_servo() -> dict[str, object]:
        """Invoke the ROS bridge servo transport after all gateway checks succeed.

        Args:
            None. The function closes over the validated request payload and runtime context.

        Returns:
            The transport result dictionary emitted by the ROS bridge.

        Raises:
            Exception: Propagates transport failures so the command pipeline can map them upstream.

        Boundary behavior:
            The helper performs no state mutation; it only forwards the validated transport call.
        """
        return await CTX.ros.servo_cartesian(axis=body.axis, delta=body.delta)

    await command.execute(plan, invoke_servo)
    return wrap_response(None, request_id)
