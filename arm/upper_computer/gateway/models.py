from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .runtime_config import load_default_calibration_payload
import json
import uuid
from urllib.parse import quote

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
    return {name: _command_policy(False, reason) for name in PUBLIC_COMMAND_NAMES}


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
        'joints': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        'gripperOpen': True,
        'homed': False,
        'limits': [False, False, False, False, False, False],
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
        'sourceEsp32StreamSemantic': 'reserved',
        'sourceEsp32StreamReserved': True,
        'sourceCameraFrameIngressLive': False,
        'sourcePerceptionLive': False,
        'rawStatus': {},
        'lastFrameAt': None,
    }


def default_calibration_profile() -> dict[str, Any]:
    payload = load_default_calibration_payload()
    metadata = payload.get('hmi_metadata', {}) if isinstance(payload, dict) else {}
    offsets = metadata.get('offsets', {}) if isinstance(metadata, dict) else {}
    return {
        'profileName': str(payload.get('version', 'default') or 'default') if isinstance(payload, dict) else 'default',
        'roi': metadata.get('roi', {'x': 0, 'y': 0, 'width': 640, 'height': 480}) if isinstance(metadata, dict) else {'x': 0, 'y': 0, 'width': 640, 'height': 480},
        'tableScaleMmPerPixel': float(metadata.get('tableScaleMmPerPixel', 1.0)) if isinstance(metadata, dict) else 1.0,
        'offsets': {
            'x': float(offsets.get('x', 0.0)) if isinstance(offsets, dict) else 0.0,
            'y': float(offsets.get('y', 0.0)) if isinstance(offsets, dict) else 0.0,
            'z': float(offsets.get('z', 0.0)) if isinstance(offsets, dict) else 0.0,
        },
        'updatedAt': str(metadata.get('updatedAt', now_iso())) if isinstance(metadata, dict) else now_iso(),
    }


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
            'storeFailures': 0,
            'lastPersistenceError': None,
            'sinkWritable': True,
            'degraded': False,
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
    """Read one field from an object or mapping without raising.

    Args:
        obj: Source object or mapping.
        name: Field or key name to read.
        default: Fallback value when the field is missing.

    Returns:
        Any: Attribute or mapping value when present, otherwise ``default``.

    Raises:
        Does not raise. Mapping inputs are supported explicitly so gateway tests
        and compatibility callers can pass decoded dictionaries without needing
        adapter wrappers.
    """
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def parse_raw_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _coerce_preview_data_url(payload: Any) -> str | None:
    """Return an image data URL from a frame payload when one is present."""
    if isinstance(payload, str) and payload.startswith('data:image/'):
        return payload
    if isinstance(payload, dict):
        for key in ('previewDataUrl', 'dataUrl', 'imageDataUrl', 'image_url'):
            value = payload.get(key)
            if isinstance(value, str) and value.startswith('data:image/'):
                return value
    return None


def _build_synthetic_preview_data_url(frame: dict[str, Any], *, width: int, height: int) -> str:
    """Build a deterministic SVG preview for synthetic/mock frames.

    The preview intentionally favors truthful operator context over photo
    realism: it visualizes the frame extent, current provider, and target
    projections so the HMI can consume a concrete frame artifact even when the
    runtime source is a synthetic scene contract.
    """
    payload = frame.get('payload') if isinstance(frame.get('payload'), dict) else {}
    targets = payload.get('targets') if isinstance(payload.get('targets'), list) else frame.get('targets', [])
    elements = [
        f"<rect x='0' y='0' width='{width}' height='{height}' rx='18' fill='#0f172a'/>",
        f"<rect x='16' y='16' width='{width - 32}' height='{height - 32}' rx='14' fill='#111827' stroke='rgba(148,163,184,0.55)'/>",
        "<text x='24' y='38' fill='#cbd5e1' font-size='16' font-family='Arial, sans-serif'>SYNTHETIC FRAME PREVIEW</text>",
    ]
    for target in targets:
        try:
            u = max(24.0, min(float(target.get('u', target.get('image_u', width / 2))), width - 24.0))
            v = max(48.0, min(float(target.get('v', target.get('image_v', height / 2))), height - 24.0))
        except Exception:
            continue
        label = str(target.get('semantic_label', target.get('target_type', 'target')) or 'target')
        confidence = float(target.get('confidence', 0.0) or 0.0)
        elements.extend([
            f"<circle cx='{u:.1f}' cy='{v:.1f}' r='18' fill='rgba(34,197,94,0.18)' stroke='#22c55e' stroke-width='2'/>",
            f"<text x='{u + 24:.1f}' y='{v - 2:.1f}' fill='#f8fafc' font-size='13' font-family='Arial, sans-serif'>{label}</text>",
            f"<text x='{u + 24:.1f}' y='{v + 16:.1f}' fill='#94a3b8' font-size='11' font-family='Arial, sans-serif'>{confidence * 100:.0f}%</text>",
        ])
    svg = f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>{''.join(elements)}</svg>"
    return f"data:image/svg+xml;charset=UTF-8,{quote(svg)}"


def map_camera_frame_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Project one camera frame-summary payload into the public HMI schema.

    Args:
        payload: Decoded runtime frame-summary envelope published by the camera
            runtime node.

    Returns:
        dict[str, Any]: Public frame projection safe for REST/WS transport.

    Raises:
        ValueError: If ``payload`` is not a dictionary with a frame object.

    Boundary behavior:
        The projection separates renderability from provider truth. ``available``
        only states that a renderable preview artifact exists. Live metadata-only
        summaries therefore stay visible to operators without fabricating a fake
        image for real camera transports.
    """
    if not isinstance(payload, dict):
        raise ValueError('frame summary payload must be a dictionary')
    frame = payload.get('frame', payload)
    if not isinstance(frame, dict):
        raise ValueError('frame summary missing frame object')
    width = int(frame.get('width', 640) or 640)
    height = int(frame.get('height', 480) or 480)
    frame_payload = frame.get('payload') if isinstance(frame.get('payload'), dict) else {}
    visual_provenance = dict(frame_payload.get('visualProvenance') or {}) if isinstance(frame_payload.get('visualProvenance'), dict) else {}
    preview_data_url = _coerce_preview_data_url(frame_payload) or _coerce_preview_data_url(frame)
    source_type = str(frame.get('sourceType', frame_payload.get('sourceType', frame_payload.get('mockProfile', 'unknown'))) or 'unknown')
    source_class = str(frame.get('sourceClass', frame_payload.get('sourceClass', visual_provenance.get('sourceClass', 'unknown'))) or 'unknown')
    frame_ingress_mode = str(payload.get('frameIngressMode', frame.get('frameIngressMode', 'unknown')) or 'unknown')
    detection_source_mode = str(frame_payload.get('detectionSourceMode', visual_provenance.get('detectionSourceMode', 'unknown')) or 'unknown')
    authoritative_target_source = str(frame_payload.get('authoritativeTargetSource', visual_provenance.get('authoritativeTargetSource', detection_source_mode)) or detection_source_mode)
    targets = frame_payload.get('targets') if isinstance(frame_payload.get('targets'), list) else []
    synthetic_preview = source_class == 'synthetic' or detection_source_mode == 'synthetic_targets' or authoritative_target_source == 'synthetic_perception'
    renderable_preview = bool(frame_payload.get('renderablePreview', visual_provenance.get('renderablePreview', preview_data_url is not None or synthetic_preview)))
    frame_ingress_live = bool(payload.get('frameIngressLive', frame.get('frameIngressLive', visual_provenance.get('frameIngressLive', frame_ingress_mode in {'synthetic_frame_stream', 'live_camera_stream'}))))
    camera_live = bool(payload.get('cameraLive', frame.get('cameraLive', visual_provenance.get('cameraLive', source_type == 'topic' or frame_ingress_mode == 'live_camera_stream'))))
    if preview_data_url is None and synthetic_preview and renderable_preview:
        preview_data_url = _build_synthetic_preview_data_url(frame, width=width, height=height)
    provider_kind = (
        'synthetic_scene' if synthetic_preview else
        'live_frame_summary' if frame_ingress_mode == 'live_camera_stream' and preview_data_url is None else
        'external_topic' if camera_live else
        'reserved_endpoint' if frame_ingress_mode == 'reserved_endpoint' else
        'frame_snapshot'
    )
    available = preview_data_url is not None
    message = '' if available else (
        'live frame metadata available; renderable frame is provided by the upstream camera bridge'
        if frame_ingress_live else
        'frame stream unavailable'
    )
    return {
        'available': available,
        'width': width,
        'height': height,
        'frameId': str(frame.get('frame_id', frame.get('frameId', 'camera_optical_frame')) or 'camera_optical_frame'),
        'source': str(payload.get('source', 'camera_runtime') or 'camera_runtime'),
        'sourceType': source_type,
        'sourceClass': source_class,
        'mockProfile': str(frame_payload.get('mockProfile', '')),
        'frameSequence': int(frame_payload.get('frameSequence', 0) or 0),
        'targetCount': len(targets),
        'previewDataUrl': preview_data_url,
        'capturedAt': now_iso(),
        'providerKind': provider_kind,
        'providerLabel': str(provider_kind if provider_kind == 'live_frame_summary' else (frame_ingress_mode or provider_kind)),
        'frameIngressMode': frame_ingress_mode,
        'frameIngressLive': frame_ingress_live,
        'cameraLive': camera_live,
        'syntheticPreview': synthetic_preview,
        'renderablePreview': renderable_preview,
        'frameTransportHealthy': frame_ingress_live,
        'authoritativeVisualSource': authoritative_target_source,
        'detectionSourceMode': detection_source_mode,
        'message': message,
        'summary': {
            'kind': str(frame_payload.get('kind', 'frame_summary') or 'frame_summary'),
            'authoritativeTargetSource': authoritative_target_source,
            'detectionSourceMode': detection_source_mode,
        },
    }


def map_system_state_message(msg: Any, ros_connected: bool | dict[str, Any], hardware_state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Project one system-state message into the public gateway schema.

    Args:
        msg: ROS message object or decoded mapping payload.
        ros_connected: Preferred boolean ROS connectivity flag. For backward
            compatibility, callers may still pass the hardware-state mapping as
            the second positional argument; that legacy form is normalized here.
        hardware_state: Optional hardware projection used to derive board/camera
            connectivity. Missing payloads degrade to an empty mapping.

    Returns:
        dict[str, Any]: Canonical public system snapshot with compatibility aliases.

    Raises:
        Does not raise. Unknown or missing fields degrade to conservative
        defaults so runtime projections stay fail-closed.
    """
    effective_ros_connected = bool(ros_connected) if isinstance(ros_connected, bool) else False
    effective_hardware_state = dict(hardware_state or {})
    if isinstance(ros_connected, dict):
        effective_hardware_state = dict(ros_connected)
        if hardware_state:
            effective_hardware_state.update(hardware_state)
    runtime_phase = normalize_runtime_phase(
        safe_getattr(msg, 'system_mode', safe_getattr(msg, 'runtimePhase', safe_getattr(msg, 'mode', None)))
    )
    emergency_stop = bool(safe_getattr(msg, 'emergency_stop', safe_getattr(msg, 'emergencyStop', False)))
    controller_mode = derive_controller_mode(
        runtime_phase,
        operator_mode=safe_getattr(msg, 'controllerMode', safe_getattr(msg, 'operatorMode', None)),
        emergency_stop=emergency_stop,
    )
    task_stage = infer_task_stage(runtime_phase, safe_getattr(msg, 'current_stage', safe_getattr(msg, 'currentStage', '')))
    return coerce_system_state_aliases({
        'runtimePhase': runtime_phase,
        'controllerMode': controller_mode,
        'taskStage': task_stage,
        'rosConnected': effective_ros_connected,
        'stm32Connected': bool(effective_hardware_state.get('sourceStm32Online', False) or safe_getattr(msg, 'hardware_ready', safe_getattr(msg, 'stm32Connected', False))),
        'esp32Connected': bool(effective_hardware_state.get('sourceEsp32Online', False) or safe_getattr(msg, 'esp32Connected', False)),
        'cameraConnected': bool(effective_hardware_state.get('sourceCameraFrameIngressLive', False) or safe_getattr(msg, 'vision_ready', safe_getattr(msg, 'cameraConnected', False))),
        'emergencyStop': emergency_stop,
        'faultCode': str(safe_getattr(msg, 'active_fault_code', safe_getattr(msg, 'faultCode', 0)) or '') or None,
        'faultMessage': str(safe_getattr(msg, 'message', safe_getattr(msg, 'faultMessage', '')) or '') or None,
        'currentTaskId': str(safe_getattr(msg, 'current_task_id', safe_getattr(msg, 'currentTaskId', '')) or ''),
        'currentStage': str(safe_getattr(msg, 'current_stage', safe_getattr(msg, 'currentStage', '')) or ''),
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
    authoritative_transport = bool(raw.get('hardwareAuthoritative', raw.get('authoritative', False)))
    simulated_transport = bool(raw.get('simulatedTransport', transport_mode == 'simulated'))
    preview_execution_only = simulated_transport or not authoritative_transport
    if simulated_transport and authoritative_transport:
        preview_execution_only = False
    execution_semantics = (
        'authoritative_simulated_transport'
        if simulated_transport and authoritative_transport else
        'preview_simulated_transport'
        if simulated_transport else
        'authoritative_real_transport'
        if hardware_present and authoritative_transport else
        'non_authoritative_real_link'
        if hardware_present else
        'unavailable'
    )
    esp32_link = raw.get('esp32_link') if isinstance(raw.get('esp32_link'), dict) else {}
    source_esp32_online = bool(safe_getattr(msg, 'esp32_online', False))
    source_camera_frame_live = bool(esp32_link.get('frame_ingress_live', raw.get('frameIngressLive', False)))
    source_perception_live = bool(raw.get('vision_ready', source_camera_frame_live))
    stream_semantic = str(esp32_link.get('stream_semantic', raw.get('streamSemantic', 'reserved')) or 'reserved')
    return {
        'joints': joints or [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        'gripperOpen': bool(gripper_open if raw_gripper_open is None else raw_gripper_open),
        'homed': bool(safe_getattr(msg, 'home_ok', False)),
        'limits': limits,
        'poseName': str(raw.get('last_stage', '') or ''),
        'busy': bool(safe_getattr(msg, 'motion_busy', False)),
        'errorCode': str(safe_getattr(msg, 'hardware_fault_code', 0) or '') or None,
        'sourceStm32Online': hardware_present,
        'sourceStm32Authoritative': authoritative_transport,
        'sourceStm32TransportMode': transport_mode,
        'sourceStm32Controllable': bool(raw.get('hardwareControllable', raw.get('controllable', False))),
        'sourceStm32Simulated': simulated_transport,
        'sourceStm32SimulatedFallback': bool(raw.get('simulatedFallback', False)),
        'sourceStm32ExecutionPreviewOnly': preview_execution_only,
        'sourceStm32ExecutionSemantics': execution_semantics,
        'sourceEsp32Online': source_esp32_online,
        'sourceEsp32StreamSemantic': stream_semantic,
        'sourceEsp32StreamReserved': bool(esp32_link.get('stream_reserved', raw.get('streamReserved', stream_semantic == 'reserved'))),
        'sourceCameraFrameIngressLive': source_camera_frame_live,
        'sourcePerceptionLive': source_perception_live,
        'rawStatus': raw,
        'lastFrameAt': now_iso() if source_camera_frame_live else None,
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
        'episodeId': envelope.get('episodeId') or envelope.get('taskRunId'),
        'stage': envelope.get('stage'),
        'errorCode': envelope.get('errorCode'),
        'operatorActionable': envelope.get('operatorActionable'),
        'event': str(safe_getattr(msg, 'event_type', 'event')),
        'message': str(envelope.get('message') or raw_message),
        'payload': payload,
    }
