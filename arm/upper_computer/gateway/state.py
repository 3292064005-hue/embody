from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any

from .models import (
    bootstrap_command_policies,
    build_command_policies,
    build_command_summary,
    build_readiness_layers,
    coerce_system_state_aliases,
    default_calibration_profile,
    default_diagnostics_summary,
    default_hardware_state,
    default_system_state,
    normalize_readiness_mode,
    now_iso,
)
from .observability import StructuredEventSink
from .readiness_snapshot import readiness_snapshot_is_stale
from .runtime_bootstrap import default_readiness_snapshot
from .generated.runtime_contract import CAPABILITY_DESCRIPTORS, COMMAND_PLANES, COMMAND_REQUIRED_BY_NAME, PRODUCT_LINE_CAPABILITIES, PUBLIC_READINESS_FIELDS, TASK_CAPABILITY_REGISTRY
from .runtime_config import (
    current_runtime_config_version,
    get_runtime_config_health,
    load_firmware_semantic_profiles,
    load_manual_command_limits,
    load_release_gate_details,
    load_runtime_promotion_receipt_details,
    load_runtime_promotion_receipts,
    resolve_active_runtime_profile,
)
from .runtime_surface import summarize_runtime_surface
from .state_slices import RecordStore, RequestContextStore, SnapshotStore, TargetProjectionStore, TaskProjectionStore, TaskRunLedgerStore


def _infer_runtime_tier(readiness: dict[str, Any], hardware: dict[str, Any]) -> tuple[str, str]:
    """Infer the operator-facing runtime tier from readiness, lane identity, and promotion truth.

    The helper accepts both the normalized readiness shape used by the gateway
    (`checks`/`commandPolicies`) and the flatter shapes often used in targeted
    tests (`motion_planner`/`commandSummary`). Runtime identity is derived from
    authoritative readiness plus the active runtime lane when that lane is known;
    current `startTask` admissibility must not demote an authoritative validated
    lane back to preview.

    Args:
        readiness: Current backend-owned readiness snapshot or a test fixture.
        hardware: Current hardware snapshot used to infer live transport truth.

    Returns:
        tuple[str, str]: The public runtime tier token and its operator-facing label.

    Boundary behavior:
        - Stale authoritative readiness always fails closed to preview.
        - When the active runtime lane is known, candidate lanes such as
          ``live_control`` cannot be surfaced as ``validated_live`` merely
          because transport and promotion are available.
        - When no runtime lane can be resolved, the helper preserves the legacy
          inference behavior so focused tests can supply only readiness/hardware.
    """
    product_lines = {str(key): dict(value) for key, value in PRODUCT_LINE_CAPABILITIES.items()}
    promotion_receipts = load_runtime_promotion_receipts()
    checks = readiness.get('checks', {}) if isinstance(readiness.get('checks'), dict) else {}
    planner = checks.get('motion_planner', {}) if isinstance(checks.get('motion_planner'), dict) else {}
    if not planner and isinstance(readiness.get('motion_planner'), dict):
        planner = dict(readiness.get('motion_planner', {}))
    command_policies = readiness.get('commandPolicies', {}) if isinstance(readiness.get('commandPolicies'), dict) else {}
    if not command_policies and isinstance(readiness.get('commandSummary'), dict):
        command_policies = dict(readiness.get('commandSummary', {}))
    planner_ready = bool(planner.get('planner_ready', planner.get('effectiveOk', planner.get('ok', False))))
    backend_authoritative = bool(readiness.get('authoritative', False))
    simulated = bool(readiness.get('simulated', False) or hardware.get('simulated', False) or hardware.get('sourceStm32Simulated', False))
    if readiness_snapshot_is_stale(readiness):
        tier = 'preview'
        return tier, str(product_lines.get(tier, {}).get('label', tier))

    runtime_profile = resolve_active_runtime_profile()
    active_profile = runtime_profile.get('activeProfile', {}) if isinstance(runtime_profile.get('activeProfile'), dict) else {}
    active_lane = str(runtime_profile.get('activeRuntimeLane', '') or '').strip()
    surface = readiness.get('executionBackboneSummary', {}) if isinstance(readiness.get('executionBackboneSummary'), dict) else {}
    if not active_profile and isinstance(surface, dict):
        active_lane = str(surface.get('activeRuntimeLane', active_lane) or active_lane).strip()
    lane_public_tier = str(active_profile.get('public_runtime_tier', '') or '').strip()
    lane_task_workbench_visible = bool(active_profile.get('task_workbench_visible', False)) if active_profile else None

    source_online = hardware.get('sourceStm32Online')
    source_authoritative = hardware.get('sourceStm32Authoritative')
    live_transport = bool((source_online if source_online is not None else not simulated) and (source_authoritative if source_authoritative is not None else not simulated) and not simulated)
    sim_promoted = bool(promotion_receipts.get('validated_sim', True))
    live_promoted = bool(promotion_receipts.get('validated_live', False))

    lane_allows_validated_sim = True
    lane_allows_validated_live = True
    if lane_public_tier:
        lane_allows_validated_sim = lane_public_tier == 'validated_sim'
        lane_allows_validated_live = lane_public_tier == 'validated_live'
    elif active_lane and lane_task_workbench_visible is False:
        lane_allows_validated_sim = False
        lane_allows_validated_live = False

    if backend_authoritative and simulated and planner_ready and sim_promoted and lane_allows_validated_sim:
        tier = 'validated_sim'
    elif backend_authoritative and live_transport and planner_ready and live_promoted and lane_allows_validated_live:
        tier = 'validated_live'
    else:
        tier = 'preview'
    if not bool(product_lines.get(tier, {}).get('publiclyExposed', True)):
        tier = 'preview'
    return tier, str(product_lines.get(tier, {}).get('label', tier))


def _build_authority_state(readiness: dict[str, Any]) -> dict[str, Any]:
    """Build one operator-facing authority-state projection.

    The projection separates backend/runtime authority from command availability
    so local preview and bootstrap states never masquerade as authoritative task
    execution lanes.
    """
    source = str(readiness.get('source', '') or '')
    runtime_surface = readiness.get('executionBackboneSummary', {}) if isinstance(readiness.get('executionBackboneSummary'), dict) else {}
    authoritative_runtime = bool(readiness.get('authoritative', False))
    authoritative_transport = bool(runtime_surface.get('authoritativeTransport', False))
    local_preview = source == 'gateway_dev_simulation' and not authoritative_runtime
    bootstrap = source in {'gateway_bootstrap', 'bootstrap'} and not authoritative_runtime
    level = 'bootstrap'
    detail = 'waiting for authoritative readiness snapshot'
    if authoritative_runtime and authoritative_transport:
        level = 'authoritative_transport'
        detail = 'authoritative runtime and execution transport are active'
    elif authoritative_runtime:
        level = 'authoritative_runtime'
        detail = 'authoritative runtime is active but execution transport is limited'
    elif local_preview:
        level = 'local_preview'
        detail = 'gateway-local preview only; maintenance commands may be projected locally'
    elif bootstrap:
        level = 'bootstrap'
        detail = 'gateway bootstrap is waiting for the runtime authority surface'
    else:
        level = 'non_authoritative'
        detail = 'non-authoritative runtime surface remains fail-closed for task execution'
    manual_ready = any(
        bool(((readiness.get('commandPolicies', {}) if isinstance(readiness.get('commandPolicies'), dict) else {}).get(name, {}) or {}).get('allowed', False))
        for name in ('jog', 'servoCartesian', 'gripper', 'home', 'resetFault', 'recover', 'stopTask')
    )
    return {
        'level': level,
        'authoritativeRuntime': authoritative_runtime,
        'authoritativeTransport': authoritative_transport,
        'localPreview': local_preview,
        'bootstrap': bootstrap,
        'maintenanceCommandReady': manual_ready,
        'detail': detail,
    }


def _build_command_surface_state(readiness: dict[str, Any]) -> dict[str, Any]:
    """Build one operator-facing command-surface projection."""
    source = str(readiness.get('source', '') or '')
    policies = {str(name): dict(payload) for name, payload in (readiness.get('commandPolicies', {}) if isinstance(readiness.get('commandPolicies'), dict) else {}).items() if isinstance(payload, dict)}
    summary = readiness.get('commandSummary', {}) if isinstance(readiness.get('commandSummary'), dict) else {}
    allowed = [str(name) for name in summary.get('allowed', []) if str(name).strip()]
    blocked = [str(name) for name in summary.get('blocked', []) if str(name).strip()]
    interactive = bool(allowed)
    surface = 'authoritative_public'
    detail = 'command surface is published from authoritative runtime policies'
    if source == 'gateway_dev_simulation':
        surface = 'local_preview'
        detail = 'command surface is gateway-local preview and remains non-authoritative'
    elif source in {'gateway_bootstrap', 'bootstrap'}:
        surface = 'bootstrap'
        detail = 'command surface is fail-closed until authoritative readiness arrives'
    elif not bool(readiness.get('authoritative', False)):
        surface = 'non_authoritative'
        detail = 'command surface is visible but not backed by authoritative runtime ownership'
    return {
        'surface': surface,
        'interactive': interactive,
        'allowedCommands': allowed,
        'blockedCommands': blocked,
        'readyCount': int(summary.get('readyCount', len(allowed)) or 0),
        'blockedCount': int(summary.get('blockedCount', len(blocked)) or 0),
        'startTaskAllowed': bool((policies.get('startTask', {}) or {}).get('allowed', False)),
        'detail': detail,
    }


def _collect_command_missing_details(readiness: dict[str, Any], command_name: str) -> tuple[list[str], list[dict[str, str]]]:
    """Return one stable missing-check projection for a public command policy.

    Args:
        readiness: Current readiness snapshot containing backend-owned checks.
        command_name: Public command key from the generated runtime contract.

    Returns:
        tuple[list[str], list[dict[str, str]]]: Missing check names plus
        normalized detail payloads for operator-facing display.

    Boundary behavior:
        Unknown commands or malformed checks fail closed by returning empty
        collections instead of raising.
    """
    checks = readiness.get('checks', {}) if isinstance(readiness.get('checks'), dict) else {}
    required = COMMAND_REQUIRED_BY_NAME.get(command_name, ())
    missing_names: list[str] = []
    missing_details: list[dict[str, str]] = []
    for name in required:
        payload = checks.get(name, {}) if isinstance(checks.get(name), dict) else {}
        ok = bool(payload.get('effectiveOk', payload.get('ok', False)))
        if ok:
            continue
        normalized_name = str(name).strip()
        detail = str(payload.get('detail', '') or '').strip() or 'not ready'
        missing_names.append(normalized_name)
        missing_details.append({'name': normalized_name, 'detail': detail})
    return missing_names, missing_details


def _build_task_execution_state(readiness: dict[str, Any], feature_state: dict[str, Any]) -> dict[str, Any]:
    """Build one operator-facing task-execution projection.

    Args:
        readiness: Current readiness snapshot.
        feature_state: Product-line feature projection derived from the public tier.

    Returns:
        dict[str, Any]: Task-workbench visibility, start-task interactivity, and
        explicit missing-check detail used by frontend operators.

    Boundary behavior:
        Missing checks are always reported explicitly when startTask is blocked
        by readiness so the workbench can stay visible without hiding the cause.
    """
    start_policy = readiness.get('commandPolicies', {}).get('startTask', {}) if isinstance(readiness.get('commandPolicies'), dict) else {}
    missing_checks, missing_details = _collect_command_missing_details(readiness, 'startTask')
    return {
        'workbenchVisible': bool(feature_state.get('taskWorkbenchVisible', False)),
        'interactive': bool(feature_state.get('taskExecutionInteractive', False)),
        'startAllowed': bool(start_policy.get('allowed', False)),
        'runtimeTier': str(feature_state.get('runtimeTier', readiness.get('runtimeTier', 'preview')) or 'preview'),
        'reason': str(feature_state.get('taskStartReason', '') or start_policy.get('reason', '') or 'task execution is fail-closed'),
        'promotionControlled': bool(feature_state.get('promotionControlled', False)),
        'promotionEffective': bool(feature_state.get('promotionEffective', False)),
        'promotionMissing': [str(value) for value in feature_state.get('promotionMissing', []) if str(value).strip()],
        'startMissingChecks': missing_checks,
        'startMissingDetails': missing_details,
    }


def _build_runtime_fingerprint(readiness: dict[str, Any]) -> str:
    """Return one stable operator-facing runtime fingerprint."""
    runtime_surface = readiness.get('executionBackboneSummary', {}) if isinstance(readiness.get('executionBackboneSummary'), dict) else {}
    requested_profile = str(runtime_surface.get('requestedRuntimeProfile', '') or '')
    active_lane = str(runtime_surface.get('activeRuntimeLane', '') or '')
    config_version = str(readiness.get('runtimeConfigVersion', '') or '')
    parts = [
        str(readiness.get('runtimeTier', 'preview') or 'preview'),
        str(readiness.get('source', '') or ''),
        str(readiness.get('runtimeDeliveryTrack', '') or ''),
        str(readiness.get('executionBackbone', '') or ''),
        requested_profile,
        active_lane,
        'auth' if bool(readiness.get('authoritative', False)) else 'nonauth',
        'sim' if bool(readiness.get('simulated', False)) else 'live',
        config_version[:24],
    ]
    return '|'.join(part for part in parts if part)


def _build_runtime_surface_state(readiness: dict[str, Any]) -> dict[str, Any]:
    """Project one single operator-facing runtime surface summary.

    The summary compresses product-line visibility, public command planes,
    runtime-interface gating, authority layering, and runtime identity into one
    surface used by UI diagnostics so operator-facing documentation does not
    need to reason across several raw contract layers.
    """
    feature_state = _build_runtime_feature_state(readiness)
    authority_state = _build_authority_state(readiness)
    command_surface_state = _build_command_surface_state(readiness)
    task_execution_state = _build_task_execution_state(readiness, feature_state)
    command_planes = {str(name): dict(payload) for name, payload in COMMAND_PLANES.items()}
    capability_descriptors = {str(name): dict(payload) for name, payload in CAPABILITY_DESCRIPTORS.items()}
    runtime_interfaces = TASK_CAPABILITY_REGISTRY.get('runtime_interfaces', {}) if isinstance(TASK_CAPABILITY_REGISTRY, dict) else {}
    public_planes = [name for name, payload in command_planes.items() if str(payload.get('dispatch_mode', '')) != 'observability_only']
    observability_planes = [name for name in command_planes if name not in public_planes]
    active_runtime_interfaces = [name for name, payload in runtime_interfaces.items() if isinstance(payload, dict) and str(payload.get('state', '')) == 'active']
    hidden_runtime_interfaces = [name for name, payload in runtime_interfaces.items() if isinstance(payload, dict) and str(payload.get('state', '')) != 'active']
    runtime_fingerprint = _build_runtime_fingerprint(readiness)
    runtime_surface = readiness.get('executionBackboneSummary', {}) if isinstance(readiness.get('executionBackboneSummary'), dict) else {}
    return {
        'runtimeTier': feature_state['runtimeTier'],
        'runtimeBadge': feature_state['runtimeBadge'],
        'runtimeLabel': feature_state['runtimeLabel'],
        'taskWorkbenchVisible': feature_state['taskWorkbenchVisible'],
        'taskExecutionInteractive': feature_state['taskExecutionInteractive'],
        'runtimeDeliveryTrack': str(readiness.get('runtimeDeliveryTrack', '') or ''),
        'executionBackbone': str(readiness.get('executionBackbone', '') or ''),
        'declaredExecutionBackbone': str(runtime_surface.get('declaredExecutionBackbone', runtime_surface.get('executionBackbone', '')) or ''),
        'declaredExecutionMode': str(runtime_surface.get('declaredExecutionMode', runtime_surface.get('executionMode', '')) or ''),
        'effectiveExecutionBackbone': str(runtime_surface.get('effectiveExecutionBackbone', '') or ''),
        'effectiveExecutionMode': str(runtime_surface.get('effectiveExecutionMode', '') or ''),
        'effectiveTransportReady': bool(runtime_surface.get('effectiveTransportReady', False)),
        'publicCommandPlanes': public_planes,
        'observabilityCommandPlanes': observability_planes,
        'runtimeGatewayEntrypoints': sorted({str(command_planes[name].get('entrypoint', '') or '') for name in public_planes if str(command_planes[name].get('entrypoint', '') or '')}),
        'activeRuntimeInterfaces': active_runtime_interfaces,
        'hiddenRuntimeInterfaces': hidden_runtime_interfaces,
        'capabilityDescriptorKeys': sorted(capability_descriptors.keys()),
        'authorityState': authority_state,
        'commandSurfaceState': command_surface_state,
        'taskExecutionState': task_execution_state,
        'runtimeFingerprint': runtime_fingerprint,
        'configHealth': get_runtime_config_health(),
    }


def _build_runtime_feature_state(readiness: dict[str, Any]) -> dict[str, Any]:
    """Project one operator-facing runtime feature state from product-line truth.

    Args:
        readiness: Current readiness snapshot with runtime tier and command policies.

    Returns:
        dict[str, Any]: Stable runtime feature payload used by frontend/UI.

    Raises:
        Does not raise. Unknown tiers fail closed to preview.

    Boundary behavior:
        Missing or partial readiness snapshots degrade to preview-visible and
        non-interactive workbench semantics.
    """
    runtime_tier = str(readiness.get('runtimeTier', 'preview') or 'preview')
    product_line = dict(PRODUCT_LINE_CAPABILITIES.get(runtime_tier, PRODUCT_LINE_CAPABILITIES.get('preview', {})) or {})
    start_policy = readiness.get('commandPolicies', {}).get('startTask', {}) if isinstance(readiness.get('commandPolicies'), dict) else {}
    start_allowed = bool(start_policy.get('allowed', False))
    task_workbench_visible = bool(product_line.get('taskWorkbenchVisible', False))
    task_execution_interactive = bool(product_line.get('taskExecutionInteractive', False)) and start_allowed and task_workbench_visible
    _, missing_details = _collect_command_missing_details(readiness, 'startTask')
    if task_workbench_visible and not start_allowed and missing_details:
        reason = '任务工作台已开放，但当前缺少 startTask 前提：' + ' / '.join(f"{item['name']}({item['detail']})" for item in missing_details)
    else:
        reason = str(start_policy.get('reason', '') or product_line.get('description', '') or 'preview runtime is fail-closed')
    return {
        'authoritativeRuntime': bool(task_workbench_visible),
        'previewRuntime': not bool(task_workbench_visible),
        'runtimeTier': runtime_tier,
        'runtimeLabel': str(product_line.get('label', runtime_tier)),
        'runtimeBadge': str(product_line.get('runtimeBadge', runtime_tier.upper())),
        'promotionControlled': bool(product_line.get('promotionControlled', False)),
        'promotionEffective': bool(product_line.get('promotionEffective', False)),
        'promotionMissing': [str(value) for value in product_line.get('promotionMissing', []) if str(value).strip()],
        'taskWorkbenchVisible': bool(task_workbench_visible),
        'taskExecutionInteractive': bool(task_execution_interactive),
        'taskStartReason': reason,
    }


class GatewayState:
    """Thread-safe gateway projection state.

    The gateway now composes dedicated stores for task, target, record, request
    context, and snapshot projections. External callers keep the same facade API,
    but the internal mutable surface is no longer one large ad-hoc container.
    """

    def __init__(self, sink: StructuredEventSink | None = None) -> None:
        self._lock = RLock()
        self._sink = sink
        self._system_store = SnapshotStore(default_system_state)
        self._hardware_store = SnapshotStore(default_hardware_state)
        self._calibration_store = SnapshotStore(default_calibration_profile)
        self._readiness_store = SnapshotStore(default_readiness_snapshot)
        self._diagnostics_store = SnapshotStore(default_diagnostics_summary)
        self._vision_frame_store = SnapshotStore(lambda: {'available': False, 'message': 'frame stream unavailable', 'providerKind': 'unavailable', 'providerLabel': 'unavailable', 'frameIngressMode': 'unavailable', 'frameIngressLive': False, 'cameraLive': False, 'syntheticPreview': False, 'frameTransportHealthy': False, 'authoritativeVisualSource': '', 'targetCount': 0})
        self._request_contexts = RequestContextStore()
        self._task_run_store = RecordStore('task_runs', sink=sink)
        self._task_store = TaskProjectionStore(self._request_contexts, ledger=TaskRunLedgerStore(self._task_run_store))
        self._target_store = TargetProjectionStore()
        self._log_store = RecordStore('logs', sink=sink)
        self._audit_store = RecordStore('audits', sink=sink)
        self._command_receipt_store = RecordStore('command_receipts', sink=sink)
        self._calibration_versions: list[dict[str, Any]] = []
        self._last_gripper_open = True
        self._backend_readiness_authoritative = False
        self._backend_diagnostics_authoritative = False

    def timestamp(self) -> str:
        return now_iso()

    def _local_readiness_mutable(self) -> bool:
        """Return whether gateway-local readiness derivation is allowed.

        Returns:
            False by default. Readiness is treated as an externally supplied
            snapshot rather than a gateway-local policy engine.
        """
        return False

    def set_controller_mode(self, mode: str) -> dict[str, Any]:
        """Update the canonical controller-mode projection."""
        with self._lock:
            system = self._system_store.mutate()
            system['controllerMode'] = mode
            system.update(coerce_system_state_aliases(system, timestamp=now_iso()))
            self._refresh_readiness_locked()
            self._refresh_diagnostics_locked()
            return self._system_store.get()

    def set_operator_mode(self, mode: str) -> dict[str, Any]:
        """Compatibility wrapper for older callers."""
        return self.set_controller_mode(mode)

    def set_calibration(self, profile: dict[str, Any]) -> None:
        with self._lock:
            self._calibration_store.set(profile)
            if self._local_readiness_mutable():
                readiness = self._readiness_store.mutate()
                readiness['checks']['calibration'] = {'ok': True, 'detail': 'profile_loaded'}
                readiness['updatedAt'] = now_iso()
            self._refresh_readiness_locked()
            self._refresh_diagnostics_locked()

    def get_calibration(self) -> dict[str, Any]:
        with self._lock:
            return self._calibration_store.get()

    def set_calibration_versions(self, versions: list[dict[str, Any]]) -> None:
        with self._lock:
            self._calibration_versions = deepcopy(versions)
            if self._local_readiness_mutable():
                readiness = self._readiness_store.mutate()
                readiness['checks']['profiles'] = {
                    'ok': bool(versions),
                    'detail': 'profiles_loaded' if versions else 'profile_missing',
                }
                readiness['updatedAt'] = now_iso()
            self._refresh_readiness_locked()
            self._refresh_diagnostics_locked()

    def get_calibration_versions(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._calibration_versions)

    def set_system(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._system_store.set(coerce_system_state_aliases(payload, timestamp=now_iso()))
            self._refresh_readiness_locked()
            self._refresh_diagnostics_locked()

    def get_system(self) -> dict[str, Any]:
        with self._lock:
            return self._system_store.get()

    def set_hardware(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._hardware_store.set(payload)
            hardware = self._hardware_store.mutate()
            self._last_gripper_open = bool(hardware.get('gripperOpen', self._last_gripper_open))
            hardware_ok = bool(hardware.get('sourceStm32Controllable', False)) and not bool(hardware.get('errorCode')) and not any(bool(v) for v in hardware.get('limits', []))
            hardware_detail = 'hardware_ready' if hardware_ok else ('fault' if hardware.get('errorCode') else 'offline')
            camera_ok = bool(hardware.get('sourceCameraFrameIngressLive', False))
            if self._local_readiness_mutable():
                readiness = self._readiness_store.mutate()
                readiness['checks']['hardware_bridge'] = {'ok': hardware_ok, 'detail': hardware_detail}
                camera_detail = 'online' if camera_ok else 'camera_offline'
                readiness['checks']['camera'] = {'ok': camera_ok, 'detail': camera_detail}
                readiness['checks']['camera_alive'] = {'ok': camera_ok, 'detail': camera_detail}
                if not camera_ok:
                    readiness['checks']['perception_alive'] = {'ok': False, 'detail': 'perception_offline'}
                    readiness['checks']['target_available'] = {'ok': False, 'detail': 'target_unavailable'}
                readiness['updatedAt'] = now_iso()
            self._refresh_readiness_locked()
            self._refresh_diagnostics_locked()

    def get_hardware(self) -> dict[str, Any]:
        with self._lock:
            return self._hardware_store.get()

    def get_last_gripper_open(self) -> bool:
        with self._lock:
            return self._last_gripper_open

    def set_gripper_open(self, value: bool) -> None:
        with self._lock:
            self._last_gripper_open = bool(value)
            self._hardware_store.mutate()['gripperOpen'] = bool(value)
            self._refresh_diagnostics_locked()

    def upsert_target(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._target_store.upsert(payload)
            if self._local_readiness_mutable():
                readiness = self._readiness_store.mutate()
                readiness['checks']['camera'] = {'ok': True, 'detail': 'target_streaming'}
                readiness['checks']['camera_alive'] = {'ok': True, 'detail': 'camera_streaming'}
                readiness['checks']['perception_alive'] = {'ok': True, 'detail': 'targets_streaming'}
                readiness['checks']['target_available'] = {'ok': True, 'detail': 'target_available'}
                readiness['updatedAt'] = now_iso()
            self._refresh_readiness_locked()
            self._refresh_diagnostics_locked()

    def replace_targets(self, payloads: list[dict[str, Any]]) -> None:
        with self._lock:
            self._target_store.replace_all(payloads)
            self._refresh_readiness_locked()
            self._refresh_diagnostics_locked()

    def clear_targets(self) -> int:
        with self._lock:
            count = self._target_store.clear()
            if self._local_readiness_mutable():
                self._readiness_store.mutate()['checks']['target_available'] = {'ok': False, 'detail': 'target_unavailable'}
            self._refresh_diagnostics_locked()
            return count

    def prune_targets(self, keep_after_seconds: float = 2.5) -> int:
        with self._lock:
            count = self._target_store.prune(keep_after_seconds=keep_after_seconds)
            if self._local_readiness_mutable() and not self._target_store.has_targets():
                self._readiness_store.mutate()['checks']['target_available'] = {'ok': False, 'detail': 'target_unavailable'}
            self._refresh_diagnostics_locked()
            return count

    def get_targets(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._target_store.ordered_public()

    def set_vision_frame(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._vision_frame_store.set(payload)

    def get_vision_frame(self) -> dict[str, Any]:
        with self._lock:
            return self._vision_frame_store.get()

    def append_log(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            appended = self._log_store.append(record)
            self._refresh_diagnostics_locked()
            return appended

    def get_logs(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._log_store.get()

    def append_audit(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            appended = self._audit_store.append(record)
            self._refresh_diagnostics_locked()
            return appended

    def get_audits(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._audit_store.get()

    def append_command_receipt(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            appended = self._command_receipt_store.append(record)
            self._refresh_diagnostics_locked()
            return appended

    def get_command_receipts(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._command_receipt_store.get()

    def attach_request_context(
        self,
        task_id: str,
        request_id: str,
        *,
        correlation_id: str | None = None,
        task_run_id: str | None = None,
        episode_id: str | None = None,
    ) -> tuple[str, str, str]:
        """Attach request/correlation identifiers to one task id.

        Args:
            task_id: Stable task identifier.
            request_id: External request identifier from the initiating API call.
            correlation_id: Optional distributed-trace style correlation id.
            task_run_id: Optional stable task-run identifier.

        Returns:
            tuple[str, str, str]: Effective `(request_id, correlation_id, task_run_id)`.

        Raises:
            Does not raise. The identifiers are stored in-memory only.
        """
        with self._lock:
            request_id_value, correlation_value, task_run_value, _episode_value = self._request_contexts.attach(
                task_id,
                request_id,
                correlation_id=correlation_id,
                task_run_id=task_run_id,
                episode_id=episode_id,
            )
            return request_id_value, correlation_value, task_run_value

    def request_context(self, task_id: str) -> tuple[str | None, str | None, str | None]:
        with self._lock:
            request_id_value, correlation_value, task_run_value, _episode_value = self._request_contexts.get(task_id)
            return request_id_value, correlation_value, task_run_value


    def request_context_payload(self, task_id: str) -> dict[str, str] | None:
        with self._lock:
            return self._request_contexts.get_payload(task_id)

    def start_task(
        self,
        task_id: str,
        frontend_task_type: str,
        target_category: str | None = None,
        request_id: str | None = None,
        *,
        correlation_id: str | None = None,
        task_run_id: str | None = None,
        episode_id: str | None = None,
        template_id: str | None = None,
        place_profile: str | None = None,
        runtime_tier: str | None = None,
        graph_key: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            task = self._task_store.start(
                task_id=task_id,
                frontend_task_type=frontend_task_type,
                target_category=target_category,
                request_id=request_id,
                system_state=self._system_store.mutate(),
                correlation_id=correlation_id,
                task_run_id=task_run_id,
                episode_id=episode_id,
                template_id=template_id,
                place_profile=place_profile,
                runtime_tier=runtime_tier,
                graph_key=graph_key,
            )
            self._refresh_readiness_locked()
            self._refresh_diagnostics_locked()
            return task

    def sync_task_from_system(self, system_payload: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            task = self._task_store.sync_from_system(system_payload, self._system_store.mutate())
            self._refresh_diagnostics_locked()
            return task

    def update_task_from_log(self, record: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
        with self._lock:
            task, changed = self._task_store.update_from_log(record, self._system_store.mutate())
            self._refresh_diagnostics_locked()
            return task, changed

    def get_current_task(self) -> dict[str, Any] | None:
        with self._lock:
            return self._task_store.get_current()

    def get_task_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._task_store.get_history()

    def update_readiness(self, name: str, ok: bool, detail: str) -> None:
        """Update a single readiness check in fallback/local mode.

        Args:
            name: Readiness check name.
            ok: Whether the check is currently healthy.
            detail: Human-readable status detail.
        """
        with self._lock:
            if self._backend_readiness_authoritative:
                return
            readiness = self._readiness_store.mutate()
            readiness['checks'][name] = {'ok': bool(ok), 'detail': detail}
            readiness['updatedAt'] = now_iso()
            self._refresh_readiness_locked()
            self._refresh_diagnostics_locked()

    def set_readiness_snapshot(self, payload: dict[str, Any], *, authoritative: bool = True) -> None:
        """Replace the cached readiness snapshot.

        Args:
            payload: Decoded readiness snapshot from ROS2/backend or an explicit
                simulated-runtime profile.
            authoritative: Whether the snapshot comes from the backend runtime and
                should be treated as the source of truth for readiness semantics.
        """
        with self._lock:
            self._backend_readiness_authoritative = bool(authoritative)
            self._readiness_store.set(payload)
            readiness = self._readiness_store.mutate()
            if 'checks' not in readiness:
                readiness['checks'] = {}
            readiness.setdefault('updatedAt', now_iso())
            self._refresh_readiness_locked()
            self._refresh_diagnostics_locked()

    def _refresh_readiness_locked(self) -> None:
        readiness = self._readiness_store.mutate()
        readiness.setdefault('checks', {})
        readiness.setdefault('updatedAt', now_iso())
        readiness.setdefault('requiredChecks', [])
        readiness.setdefault('runtimeRequiredChecks', [])
        readiness.setdefault('missingChecks', [])
        readiness.setdefault('runtimeMissingChecks', [])
        readiness.setdefault('missingDetails', [])
        readiness.setdefault('runtimeHealthy', False)
        readiness.setdefault('modeReady', False)
        readiness.setdefault('allReady', False)
        readiness.setdefault('commandPolicies', {})
        readiness.setdefault('commandSummary', build_command_summary(readiness.get('commandPolicies', {})))
        readiness.setdefault('mode', 'bootstrap')
        readiness.setdefault('source', 'backend' if self._backend_readiness_authoritative else readiness.get('source', 'gateway_bootstrap'))
        readiness.setdefault('authoritative', bool(self._backend_readiness_authoritative))
        readiness.setdefault('simulated', False)
        manual_limits = load_manual_command_limits()
        readiness['manualCommandLimits'] = {
            'maxServoCartesianDeltaMeters': float(manual_limits.get('max_servo_cartesian_delta', 0.1)),
            'maxJogJointStepDeg': float(manual_limits.get('max_jog_joint_step_deg', 10.0)),
        }
        readiness['runtimeConfigVersion'] = current_runtime_config_version()
        system = self._system_store.mutate()
        snapshot_mode_locked = self._backend_readiness_authoritative or readiness.get('source') in {'gateway_bootstrap'} or readiness.get('mode') in {'bootstrap'}
        if not snapshot_mode_locked:
            readiness['mode'] = normalize_readiness_mode(system) if system else readiness.get('mode', 'bootstrap')
        readiness['controllerMode'] = system.get('controllerMode', system.get('operatorMode', readiness.get('controllerMode', 'idle')))
        readiness['runtimePhase'] = system.get('runtimePhase', system.get('mode', readiness.get('runtimePhase', 'boot')))
        readiness['taskStage'] = system.get('taskStage', system.get('currentStage', readiness.get('taskStage', 'created')))
        runtime_healthy, mode_ready = build_readiness_layers(str(readiness.get('mode', 'bootstrap')), dict(readiness.get('checks') or {}))
        local_preview_only = str(readiness.get('source', '') or '') == 'gateway_dev_simulation' and not self._backend_readiness_authoritative
        if not self._backend_readiness_authoritative:
            readiness['commandPolicies'] = build_command_policies(str(readiness.get('mode', 'bootstrap')), dict(readiness.get('checks') or {}))
        if self._backend_readiness_authoritative:
            readiness['runtimeHealthy'] = bool(readiness.get('runtimeHealthy', runtime_healthy))
            readiness['modeReady'] = bool(readiness.get('modeReady', mode_ready))
        elif local_preview_only:
            readiness['runtimeHealthy'] = False
            readiness['modeReady'] = False
        else:
            readiness['runtimeHealthy'] = runtime_healthy
            readiness['modeReady'] = mode_ready
        readiness['allReady'] = readiness['modeReady']
        readiness['authoritative'] = bool(self._backend_readiness_authoritative) if 'authoritative' not in readiness else bool(readiness.get('authoritative'))
        if readiness_snapshot_is_stale(readiness):
            stale_reason = 'authoritative readiness snapshot stale'
            readiness['runtimeHealthy'] = False
            readiness['modeReady'] = False
            readiness['allReady'] = False
            readiness['commandPolicies'] = bootstrap_command_policies(stale_reason)
            missing_details = [str(item) for item in list(readiness.get('missingDetails') or []) if str(item).strip()]
            if stale_reason not in missing_details:
                missing_details.append(stale_reason)
            readiness['missingDetails'] = missing_details
        readiness['commandSummary'] = build_command_summary(readiness.get('commandPolicies', {}))
        hardware = self._hardware_store.mutate()
        tier, product_line = _infer_runtime_tier(readiness, hardware)
        readiness['runtimeTier'] = tier
        readiness['productLine'] = product_line
        runtime_surface = summarize_runtime_surface(
            runtime_tier=tier,
            readiness=readiness,
            hardware=hardware,
            runtime_profile_details=resolve_active_runtime_profile(),
            firmware_profiles=load_firmware_semantic_profiles(),
        )
        readiness['runtimeDeliveryTrack'] = runtime_surface['runtimeDeliveryTrack']
        readiness['executionBackbone'] = runtime_surface['executionBackbone']
        readiness['executionBackboneSummary'] = runtime_surface
        readiness['promotionReceipts'] = load_runtime_promotion_receipt_details()
        readiness['releaseGates'] = load_release_gate_details()
        readiness['commandPlanes'] = {str(name): dict(payload) for name, payload in COMMAND_PLANES.items()}
        readiness['capabilityDescriptors'] = {str(name): dict(payload) for name, payload in CAPABILITY_DESCRIPTORS.items()}
        readiness['runtimeFeatureState'] = _build_runtime_feature_state(readiness)
        readiness['authorityState'] = _build_authority_state(readiness)
        readiness['commandSurfaceState'] = _build_command_surface_state(readiness)
        readiness['taskExecutionState'] = _build_task_execution_state(readiness, readiness['runtimeFeatureState'])
        readiness['runtimeFingerprint'] = _build_runtime_fingerprint(readiness)
        readiness['runtimeSurfaceState'] = _build_runtime_surface_state(readiness)
        readiness['firmwareSemanticProfile'] = runtime_surface['firmwareProfile']
        readiness['firmwareSemanticMessage'] = runtime_surface['firmwareMessage']

    def _public_readiness_payload(self, readiness: dict[str, Any]) -> dict[str, Any]:
        public_fields = set(PUBLIC_READINESS_FIELDS) | {'mode', 'controllerMode', 'runtimePhase', 'taskStage'}
        return {key: deepcopy(value) for key, value in readiness.items() if key in public_fields}

    def get_readiness(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_readiness_locked()
            return self._readiness_store.get()

    def get_public_readiness(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_readiness_locked()
            return self._public_readiness_payload(self._readiness_store.get())

    def _refresh_diagnostics_locked(self) -> None:
        readiness = self._readiness_store.mutate()
        diagnostics = self._diagnostics_store.mutate()
        system = self._system_store.mutate()
        task_history = self._task_store.get_history()

        computed_ready = bool(readiness.get('allReady', False))
        computed_degraded = (not computed_ready) or (not system.get('rosConnected', False))
        computed_detail = 'ready' if computed_ready else 'degraded_runtime'

        diagnostics['updatedAt'] = now_iso()
        diagnostics['faultCount'] = self._log_store.count_fault_like()

        if self._backend_diagnostics_authoritative:
            diagnostics['ready'] = bool(diagnostics.get('ready', computed_ready))
            diagnostics['degraded'] = bool(diagnostics.get('degraded', computed_degraded))
            diagnostics['detail'] = str(diagnostics.get('detail') or computed_detail)
            if diagnostics.get('latencyMs') is None:
                diagnostics['latencyMs'] = 0 if system.get('rosConnected', False) else None
        else:
            diagnostics['ready'] = computed_ready
            diagnostics['degraded'] = computed_degraded
            diagnostics['detail'] = computed_detail
            diagnostics['latencyMs'] = 0 if system.get('rosConnected', False) else None

        if task_history:
            success_count = len([item for item in task_history if item.get('success')])
            success_rate = round((success_count / len(task_history)) * 100.0, 2)
            if not self._backend_diagnostics_authoritative or diagnostics.get('taskSuccessRate') is None:
                diagnostics['taskSuccessRate'] = success_rate
        elif not self._backend_diagnostics_authoritative:
            diagnostics['taskSuccessRate'] = None
        default_observability = default_diagnostics_summary()['observability']
        observability = dict(default_observability)
        store_failures = 0
        last_persistence_error = None
        for metrics in (
            self._log_store.persistence_metrics(),
            self._audit_store.persistence_metrics(),
            self._task_run_store.persistence_metrics(),
            self._command_receipt_store.persistence_metrics(),
        ):
            store_failures += int(metrics.get('storeFailures', 0) or 0)
            last_persistence_error = metrics.get('lastPersistenceError') or last_persistence_error
        sink = self._sink
        if sink is not None and hasattr(sink, 'metrics'):
            try:
                observability.update(sink.metrics())
            except Exception as exc:
                observability['lastError'] = str(exc)
                observability['sinkWritable'] = False
                observability['degraded'] = True
        observability['storeFailures'] = store_failures
        observability['lastPersistenceError'] = last_persistence_error
        observability['sinkWritable'] = bool(observability.get('sinkWritable', True)) and not bool(last_persistence_error)
        observability['degraded'] = bool(observability.get('degraded', False) or observability.get('lastError') or store_failures or observability.get('droppedRecords', 0))
        diagnostics['observability'] = observability

    def refresh_diagnostics(self) -> None:
        with self._lock:
            self._refresh_diagnostics_locked()

    def get_diagnostics(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_diagnostics_locked()
            return self._diagnostics_store.get()

    def set_current_task(self, task: dict[str, Any] | None) -> None:
        with self._lock:
            self._task_store.set_current(task)
            self._refresh_diagnostics_locked()

    def set_diagnostics(self, diagnostics: dict[str, Any], *, authoritative: bool = False) -> None:
        with self._lock:
            self._backend_diagnostics_authoritative = bool(authoritative)
            self._diagnostics_store.set(diagnostics)
            self._diagnostics_store.mutate()['updatedAt'] = now_iso()
