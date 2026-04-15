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
from .generated.runtime_contract import PRODUCT_LINE_CAPABILITIES
from .runtime_config import (
    current_runtime_config_version,
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
    """Infer the operator-facing runtime tier from readiness, transport truth, and promotion receipts.

    The helper accepts both the normalized readiness shape used by the gateway
    (`checks`/`commandPolicies`) and the flatter shapes often used in targeted
    tests (`motion_planner`/`commandSummary`). A runtime tier may only be exposed
    when its committed promotion receipt is present; otherwise the gateway remains
    fail-closed at preview tier.
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
    start_policy = command_policies.get('startTask', {}) if isinstance(command_policies.get('startTask'), dict) else {}
    planner_ready = bool(planner.get('planner_ready', planner.get('effectiveOk', planner.get('ok', False))))
    start_allowed = bool(start_policy.get('allowed', False))
    backend_authoritative = bool(readiness.get('authoritative', False))
    simulated = bool(readiness.get('simulated', False) or hardware.get('simulated', False) or hardware.get('sourceStm32Simulated', False))
    if readiness_snapshot_is_stale(readiness):
        tier = 'preview'
        return tier, str(product_lines.get(tier, {}).get('label', tier))
    source_online = hardware.get('sourceStm32Online')
    source_authoritative = hardware.get('sourceStm32Authoritative')
    live_transport = bool((source_online if source_online is not None else not simulated) and (source_authoritative if source_authoritative is not None else not simulated) and not simulated)
    sim_promoted = bool(promotion_receipts.get('validated_sim', True))
    live_promoted = bool(promotion_receipts.get('validated_live', False))
    if backend_authoritative and simulated and planner_ready and start_allowed and sim_promoted:
        tier = 'validated_sim'
    elif backend_authoritative and live_transport and planner_ready and start_allowed and live_promoted:
        tier = 'validated_live'
    else:
        tier = 'preview'
    return tier, str(product_lines.get(tier, {}).get('label', tier))


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
        if not self._backend_readiness_authoritative:
            readiness['commandPolicies'] = build_command_policies(str(readiness.get('mode', 'bootstrap')), dict(readiness.get('checks') or {}))
        readiness['runtimeHealthy'] = bool(readiness.get('runtimeHealthy', runtime_healthy)) if self._backend_readiness_authoritative else runtime_healthy
        readiness['modeReady'] = bool(readiness.get('modeReady', mode_ready)) if self._backend_readiness_authoritative else mode_ready
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
        readiness['firmwareSemanticProfile'] = runtime_surface['firmwareProfile']
        readiness['firmwareSemanticMessage'] = runtime_surface['firmwareMessage']

    def get_readiness(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_readiness_locked()
            return self._readiness_store.get()

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
