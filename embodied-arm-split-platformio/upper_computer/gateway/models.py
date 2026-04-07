from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json
import uuid

from .generated.runtime_contract import (
    COMPATIBILITY_ALIASES,
    HARDWARE_AUTHORITY_FIELDS,
    PUBLIC_COMMAND_NAMES,
    PUBLIC_READINESS_FIELDS,
    READINESS_REQUIRED_BY_MODE,
    RUNTIME_HEALTH_REQUIRED,
    SYSTEM_SEMANTIC_FIELDS,
    build_command_policies as _generated_build_command_policies,
    build_readiness_layers as _generated_build_readiness_layers,
    required_checks_for_mode as _generated_required_checks_for_mode,
)

try:
    from arm_backend_common.event_envelope import decode_event_message
except Exception:  # pragma: no cover
    def decode_event_message(raw):
        return None

SYSTEM_MODE_MAP = {
    0: 'boot',
    1: 'idle',
    2: 'perception',
    3: 'plan',
    4: 'execute',
    5: 'verify',
    6: 'safe_stop',
    7: 'fault',
}
RUNTIME_PHASE_VALUES = tuple(SYSTEM_MODE_MAP.values())
CONTROLLER_MODE_VALUES = ('idle', 'manual', 'task', 'maintenance')
READINESS_MODE_VALUES = ('boot', 'idle', 'task', 'manual', 'maintenance', 'safe_stop', 'fault', 'bootstrap')
RUNTIME_PHASE_TO_CONTROLLER_MODE = {
    'boot': 'idle',
    'idle': 'idle',
    'perception': 'task',
    'plan': 'task',
    'execute': 'task',
    'verify': 'task',
    'safe_stop': 'maintenance',
    'fault': 'maintenance',
}
FINAL_TASK_STAGE_BY_RUNTIME_PHASE = {
    'boot': 'created',
    'idle': 'done',
    'perception': 'perception',
    'plan': 'plan',
    'execute': 'execute',
    'verify': 'verify',
    'safe_stop': 'failed',
    'fault': 'failed',
}
FRONTEND_TO_BACKEND_TASK_TYPE = {
    'pick_place': 'PICK_AND_PLACE',
    'sort_by_color': 'PICK_BY_COLOR',
    'sort_by_qr': 'PICK_BY_QR',
    'clear_table': 'CLEAR_TABLE',
}
BACKEND_TO_FRONTEND_TASK_TYPE = {v: k for k, v in FRONTEND_TO_BACKEND_TASK_TYPE.items()} | {
    'CLASSIFY': 'sort_by_color',
    'pick_place': 'pick_place',
    'sort_by_color': 'sort_by_color',
    'sort_by_qr': 'sort_by_qr',
    'clear_table': 'clear_table',
}
DEFAULT_TASK_TEMPLATES = [
    {'id': 'pick-red', 'name': '抓取红色目标', 'taskType': 'pick_place', 'description': '单目标抓取并按红色料区放置。', 'defaultTargetCategory': 'red', 'riskLevel': 'low'},
    {'id': 'pick-blue', 'name': '抓取蓝色目标', 'taskType': 'pick_place', 'description': '单目标抓取并按蓝色料区放置。', 'defaultTargetCategory': 'blue', 'riskLevel': 'low'},
    {'id': 'sort-color', 'name': '按颜色分拣', 'taskType': 'sort_by_color', 'description': '使用颜色选择器触发分拣任务。', 'riskLevel': 'medium'},
    {'id': 'sort-qr', 'name': '按二维码分拣', 'taskType': 'sort_by_qr', 'description': '识别二维码后搬运到目标料区。', 'riskLevel': 'medium'},
    {'id': 'clear-table', 'name': '清台任务', 'taskType': 'clear_table', 'description': '持续抓取当前工作台上的全部目标。', 'riskLevel': 'high'},
]

def _command_policy(allowed: bool, reason: str) -> dict[str, Any]:
    """Build a serializable readiness command policy record.

    Args:
        allowed: Whether the command is currently permitted.
        reason: Human-readable explanation for the policy outcome.

    Returns:
        A plain dictionary that can be serialized in REST/WS readiness snapshots.
    """
    return {'allowed': bool(allowed), 'reason': str(reason)}


def build_command_policies(mode: str, checks: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Delegate command-policy derivation to the generated backend mirror."""
    return _generated_build_command_policies(mode, checks)


def bootstrap_command_policies(reason: str = 'waiting for authoritative readiness snapshot') -> dict[str, dict[str, Any]]:
    """Return fail-closed command policies used during gateway bootstrap.

    Args:
        reason: Human-readable deny reason applied to all commands.

    Returns:
        Mapping keyed by public command name.
    """
    return {
        'startTask': _command_policy(False, reason),
        'stopTask': _command_policy(False, reason),
        'jog': _command_policy(False, reason),
        'servoCartesian': _command_policy(False, reason),
        'gripper': _command_policy(False, reason),
        'home': _command_policy(False, reason),
        'resetFault': _command_policy(False, reason),
    }


def simulated_local_only_command_policies() -> dict[str, dict[str, Any]]:
    """Return explicit dev-HMI-only policies for local simulated fallback.

    Returns:
        Mapping keyed by public command name.
    """
    reason = 'dev-hmi-mock simulated runtime'
    return {
        'startTask': _command_policy(False, 'task execution requires authoritative ROS runtime readiness'),
        'stopTask': _command_policy(True, reason),
        'jog': _command_policy(True, reason),
        'servoCartesian': _command_policy(True, reason),
        'gripper': _command_policy(True, reason),
        'home': _command_policy(True, reason),
        'resetFault': _command_policy(True, reason),
    }

def build_command_summary(command_policies: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Summarize backend command policies for UI consumption."""
    allowed = [name for name, payload in command_policies.items() if bool(payload.get('allowed'))]
    blocked = [name for name in command_policies if name not in allowed]
    return {
        'allowed': allowed,
        'blocked': blocked,
        'readyCount': len(allowed),
        'blockedCount': len(blocked),
    }


def build_readiness_layers(mode: str, checks: dict[str, dict[str, Any]]) -> tuple[bool, bool]:
    """Delegate readiness-layer derivation to the generated backend mirror."""
    return _generated_build_readiness_layers(mode, checks)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def new_request_id(prefix: str = 'req') -> str:
    return f'{prefix}-{uuid.uuid4().hex[:12]}'


def new_correlation_id(prefix: str = 'corr') -> str:
    return f'{prefix}-{uuid.uuid4().hex[:12]}'


def wrap_response(data: Any, request_id: str, correlation_id: str | None = None) -> dict[str, Any]:
    return {'code': 0, 'message': 'ok', 'requestId': request_id, 'correlationId': correlation_id, 'timestamp': now_iso(), 'data': data}


def normalize_runtime_phase(mode: int | str | None) -> str:
    """Normalize backend/transport runtime mode to a stable public runtime phase.

    Args:
        mode: Integer enum, public string, or None.

    Returns:
        Stable runtime phase token.

    Boundary behavior:
        Unknown values degrade to ``idle`` to preserve forward compatibility.
    """
    if isinstance(mode, str):
        normalized = mode.strip().lower()
        return normalized if normalized in RUNTIME_PHASE_VALUES else 'idle'
    if mode is None:
        return 'idle'
    try:
        return SYSTEM_MODE_MAP.get(int(mode), 'idle')
    except Exception:
        return 'idle'


map_system_mode = normalize_runtime_phase


def normalize_controller_mode(mode: str | None) -> str:
    normalized = str(mode or 'idle').strip().lower()
    return normalized if normalized in CONTROLLER_MODE_VALUES else 'idle'


def derive_controller_mode(runtime_phase: str, *, operator_mode: str | None = None, emergency_stop: bool = False) -> str:
    explicit = normalize_controller_mode(operator_mode)
    if explicit in {'manual', 'maintenance'}:
        return explicit
    normalized_phase = normalize_runtime_phase(runtime_phase)
    if emergency_stop or normalized_phase in {'safe_stop', 'fault'}:
        return 'maintenance'
    return RUNTIME_PHASE_TO_CONTROLLER_MODE.get(normalized_phase, explicit)


def infer_task_stage(runtime_phase: str, current_stage: str = '') -> str:
    normalized = (current_stage or '').strip().lower()
    if normalized in {'created', 'queued'}:
        return 'created'
    if 'verify' in normalized:
        return 'verify'
    if normalized in {'move_to_pregrasp', 'descend', 'close_gripper', 'lift', 'move_to_place', 'open_gripper', 'retreat', 'go_home'} or 'exec' in normalized:
        return 'execute'
    if 'plan' in normalized or 'target_locked' in normalized:
        return 'plan'
    if 'wait' in normalized or 'perception' in normalized:
        return 'perception'
    return FINAL_TASK_STAGE_BY_RUNTIME_PHASE.get(normalize_runtime_phase(runtime_phase), 'created')


def infer_task_percent(runtime_phase: str, current_stage: str = '') -> int:
    normalized = (current_stage or '').strip().lower()
    mapping = {'move_to_pregrasp': 58, 'descend': 64, 'close_gripper': 70, 'lift': 76, 'move_to_place': 82, 'open_gripper': 88, 'retreat': 94, 'go_home': 97}
    if normalized in mapping:
        return mapping[normalized]
    return {'boot': 0, 'idle': 100, 'perception': 15, 'plan': 40, 'execute': 72, 'verify': 92, 'safe_stop': 100, 'fault': 100}.get(normalize_runtime_phase(runtime_phase), 0)


def coerce_system_state_aliases(payload: dict[str, Any], *, timestamp: str | None = None) -> dict[str, Any]:
    """Normalize semantic system fields while preserving legacy aliases.

    Args:
        payload: Partial system-state payload from ROS, gateway or frontend mock.
        timestamp: Optional timestamp override.

    Returns:
        Normalized system-state dictionary.

    Boundary behavior:
        Missing semantic fields are derived from the legacy aliases so callers can
        migrate incrementally without breaking existing code paths.
    """
    normalized = dict(payload)
    runtime_phase = normalize_runtime_phase(normalized.get('runtimePhase', normalized.get('mode')))
    controller_mode = derive_controller_mode(
        runtime_phase,
        operator_mode=normalized.get('controllerMode', normalized.get('operatorMode')),
        emergency_stop=bool(normalized.get('emergencyStop', False)),
    )
    task_stage = infer_task_stage(runtime_phase, str(normalized.get('taskStage', normalized.get('currentStage', '')) or ''))
    normalized['runtimePhase'] = runtime_phase
    normalized['controllerMode'] = controller_mode
    normalized['taskStage'] = task_stage
    normalized['mode'] = runtime_phase
    normalized['operatorMode'] = controller_mode
    normalized['currentStage'] = task_stage
    normalized.setdefault('currentTaskId', '')
    normalized.setdefault('rosConnected', False)
    normalized.setdefault('stm32Connected', False)
    normalized.setdefault('esp32Connected', False)
    normalized.setdefault('cameraConnected', False)
    normalized.setdefault('emergencyStop', False)
    normalized.setdefault('faultCode', None)
    normalized.setdefault('faultMessage', None)
    normalized['timestamp'] = timestamp or str(normalized.get('timestamp') or now_iso())
    return normalized


def default_system_state() -> dict[str, Any]:
    return coerce_system_state_aliases({
        'runtimePhase': 'boot',
        'controllerMode': 'idle',
        'taskStage': 'created',
        'rosConnected': False,
        'stm32Connected': False,
        'esp32Connected': False,
        'cameraConnected': False,
        'emergencyStop': False,
        'faultCode': None,
        'faultMessage': None,
        'currentTaskId': '',
    })


def default_hardware_state() -> dict[str, Any]:
    return {
        'joints': [0.0, 0.0, 0.0, 0.0, 0.0],
        'gripperOpen': True,
        'homed': False,
        'limits': [False, False, False, False, False],
        'poseName': '',
        'busy': False,
        'errorCode': None,
        'sourceStm32Online': False,
        'sourceStm32Authoritative': False,
        'sourceStm32TransportMode': 'unavailable',
        'sourceStm32Controllable': False,
        'sourceStm32Simulated': False,
        'sourceStm32SimulatedFallback': False,
        'sourceEsp32Online': False,
        'rawStatus': {},
        'lastFrameAt': None,
    }


def default_calibration_profile() -> dict[str, Any]:
    return {'profileName': 'default', 'roi': {'x': 0, 'y': 0, 'width': 640, 'height': 480}, 'tableScaleMmPerPixel': 1.0, 'offsets': {'x': 0.0, 'y': 0.0, 'z': 0.0}, 'updatedAt': now_iso()}


def default_readiness() -> dict[str, Any]:
    """Return the gateway bootstrap readiness snapshot.

    Returns:
        dict[str, Any]: Fail-closed bootstrap readiness payload.

    Raises:
        Does not raise.

    Boundary behavior:
        Delegates to :mod:`gateway.runtime_bootstrap` so bootstrap semantics stay
        isolated from the gateway's normalization helpers.
    """
    from .runtime_bootstrap import default_readiness_snapshot

    return default_readiness_snapshot()


def default_diagnostics_summary() -> dict[str, Any]:
    return {
        'ready': False,
        'latencyMs': None,
        'taskSuccessRate': None,
        'faultCount': 0,
        'degraded': True,
        'detail': 'waiting_for_runtime',
        'updatedAt': now_iso(),
        'observability': {
            'queueDepth': 0,
            'droppedRecords': 0,
            'strictSync': False,
            'lastFlushAt': None,
            'lastFlushDurationMs': None,
            'lastFsyncDurationMs': None,
            'lastError': None,
        },
    }


def normalize_readiness_mode(system: dict[str, Any]) -> str:
    controller_mode = normalize_controller_mode(system.get('controllerMode', system.get('operatorMode', 'idle')))
    runtime_phase = normalize_runtime_phase(system.get('runtimePhase', system.get('mode')))
    if bool(system.get('emergencyStop')) or runtime_phase in {'safe_stop', 'fault'}:
        return 'safe_stop' if runtime_phase == 'safe_stop' or bool(system.get('emergencyStop')) else 'fault'
    if controller_mode in {'manual', 'maintenance'}:
        return controller_mode
    if controller_mode == 'task' or runtime_phase in {'perception', 'plan', 'execute', 'verify'}:
        return 'task'
    if runtime_phase == 'boot':
        return 'boot'
    return 'idle'


def required_checks_for_mode(mode: str) -> tuple[str, ...]:
    return _generated_required_checks_for_mode(mode)


def map_task_type_from_frontend(task_type: str | None) -> str:
    return FRONTEND_TO_BACKEND_TASK_TYPE.get(task_type or '', 'PICK_AND_PLACE')


def map_task_type_from_backend(task_type: str | None) -> str:
    return BACKEND_TO_FRONTEND_TASK_TYPE.get(str(task_type or ''), 'pick_place')


def safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def parse_raw_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def map_system_state_message(msg: Any, ros_connected: bool, hardware_state: dict[str, Any] | None = None) -> dict[str, Any]:
    hardware_state = hardware_state or {}
    runtime_phase = normalize_runtime_phase(safe_getattr(msg, 'system_mode', None))
    controller_mode = derive_controller_mode(runtime_phase, emergency_stop=bool(safe_getattr(msg, 'emergency_stop', False)))
    task_stage = infer_task_stage(runtime_phase, str(safe_getattr(msg, 'current_stage', '') or ''))
    return coerce_system_state_aliases({
        'runtimePhase': runtime_phase,
        'controllerMode': controller_mode,
        'taskStage': task_stage,
        'rosConnected': bool(ros_connected),
        'stm32Connected': bool(hardware_state.get('sourceStm32Online', False) or safe_getattr(msg, 'hardware_ready', False)),
        'esp32Connected': bool(hardware_state.get('sourceEsp32Online', False)),
        'cameraConnected': bool(safe_getattr(msg, 'vision_ready', False) or hardware_state.get('sourceEsp32Online', False)),
        'emergencyStop': bool(safe_getattr(msg, 'emergency_stop', False)),
        'faultCode': str(safe_getattr(msg, 'active_fault_code', 0) or '') or None,
        'faultMessage': str(safe_getattr(msg, 'message', '') or '') or None,
        'currentTaskId': str(safe_getattr(msg, 'current_task_id', '') or ''),
        'currentStage': str(safe_getattr(msg, 'current_stage', '') or ''),
        'timestamp': now_iso(),
    })


def map_hardware_state_message(msg: Any, gripper_open: bool = True) -> dict[str, Any]:
    raw = parse_raw_json(safe_getattr(msg, 'raw_status', ''))
    joints = [float(v) for v in list(safe_getattr(msg, 'joint_position', []) or raw.get('joint_position', []))]
    limit_triggered = bool(safe_getattr(msg, 'limit_triggered', False))
    limits = [limit_triggered for _ in range(len(joints) or 1)]
    raw_gripper_open = raw.get('gripper_open')
    hardware_present = bool(raw.get('hardwarePresent', raw.get('online', safe_getattr(msg, 'stm32_online', False))))
    transport_mode = str(raw.get('transportMode', 'real' if hardware_present else 'unavailable'))
    return {
        'joints': joints or [0.0, 0.0, 0.0, 0.0, 0.0],
        'gripperOpen': bool(gripper_open if raw_gripper_open is None else raw_gripper_open),
        'homed': bool(safe_getattr(msg, 'home_ok', False)),
        'limits': limits,
        'poseName': str(raw.get('last_stage', '') or ''),
        'busy': bool(safe_getattr(msg, 'motion_busy', False)),
        'errorCode': str(safe_getattr(msg, 'hardware_fault_code', 0) or '') or None,
        'sourceStm32Online': hardware_present,
        'sourceStm32Authoritative': bool(raw.get('hardwareAuthoritative', raw.get('authoritative', False))),
        'sourceStm32TransportMode': transport_mode,
        'sourceStm32Controllable': bool(raw.get('hardwareControllable', raw.get('controllable', False))),
        'sourceStm32Simulated': bool(raw.get('simulatedTransport', transport_mode == 'simulated')),
        'sourceStm32SimulatedFallback': bool(raw.get('simulatedFallback', False)),
        'sourceEsp32Online': bool(safe_getattr(msg, 'esp32_online', False)),
        'rawStatus': raw,
        'lastFrameAt': now_iso() if safe_getattr(msg, 'esp32_online', False) else None,
    }


def map_target_message(msg: Any) -> dict[str, Any]:
    category = str(safe_getattr(msg, 'semantic_label', '') or safe_getattr(msg, 'target_type', '') or 'unknown')
    target_id = str(safe_getattr(msg, 'target_id', '') or f"{category}-{round(float(safe_getattr(msg, 'table_x', 0.0)), 4)}-{round(float(safe_getattr(msg, 'table_y', 0.0)), 4)}")
    return {
        'id': target_id,
        'category': category,
        'pixelX': float(safe_getattr(msg, 'image_u', 0.0)),
        'pixelY': float(safe_getattr(msg, 'image_v', 0.0)),
        'worldX': float(safe_getattr(msg, 'table_x', 0.0)),
        'worldY': float(safe_getattr(msg, 'table_y', 0.0)),
        'angle': float(safe_getattr(msg, 'yaw', 0.0)),
        'confidence': float(safe_getattr(msg, 'confidence', 0.0)),
        'graspable': bool(safe_getattr(msg, 'is_valid', True)) and float(safe_getattr(msg, 'confidence', 0.0)) >= 0.5,
        '_receivedAt': now_iso(),
    }


def map_log_event_message(msg: Any) -> dict[str, Any]:
    timestamp = now_iso()
    level = str(safe_getattr(msg, 'level', 'INFO') or 'INFO').lower()
    raw_message = str(safe_getattr(msg, 'message', ''))
    envelope = decode_event_message(raw_message) or {}
    payload = dict(envelope.get('payload') or {})
    payload.setdefault('code', int(safe_getattr(msg, 'code', 0) or 0))
    return {
        'id': f'log-{uuid.uuid4().hex[:12]}',
        'timestamp': timestamp,
        'level': level if level in {'info', 'warn', 'error', 'fault'} else 'info',
        'module': str(safe_getattr(msg, 'source', 'ros2')),
        'taskId': str(safe_getattr(msg, 'task_id', '') or '') or None,
        'requestId': envelope.get('requestId'),
        'correlationId': envelope.get('correlationId'),
        'taskRunId': envelope.get('taskRunId'),
        'stage': envelope.get('stage'),
        'errorCode': envelope.get('errorCode'),
        'operatorActionable': envelope.get('operatorActionable'),
        'event': str(safe_getattr(msg, 'event_type', 'event')),
        'message': str(envelope.get('message') or raw_message),
        'payload': payload,
    }
