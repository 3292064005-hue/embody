from __future__ import annotations

"""Generated gateway runtime-contract mirror. Do not edit manually."""

from typing import Any, Iterable

PUBLIC_READINESS_FIELDS = ('runtimeHealthy', 'modeReady', 'allReady', 'runtimeRequiredChecks', 'runtimeMissingChecks', 'requiredChecks', 'missingChecks', 'missingDetails', 'checks', 'commandPolicies', 'commandSummary', 'authoritative', 'simulated', 'runtimeTier', 'productLine', 'runtimeDeliveryTrack', 'executionBackbone', 'executionBackboneSummary', 'promotionReceipts', 'releaseGates', 'firmwareSemanticProfile', 'firmwareSemanticMessage', 'manualCommandLimits', 'runtimeConfigVersion', 'source', 'updatedAt')
RUNTIME_HEALTH_REQUIRED = ('ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'scene_runtime_service', 'grasp_runtime_service', 'hardware_bridge', 'calibration', 'profiles')
READINESS_REQUIRED_BY_MODE = {'boot': ('ros2',), 'idle': ('ros2', 'task_orchestrator', 'hardware_bridge', 'calibration', 'profiles'), 'task': ('ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'scene_runtime_service', 'grasp_runtime_service', 'hardware_bridge', 'camera_alive', 'perception_alive', 'target_available', 'calibration', 'profiles'), 'manual': ('ros2', 'task_orchestrator', 'hardware_bridge'), 'maintenance': ('ros2', 'task_orchestrator', 'hardware_bridge'), 'safe_stop': ('ros2', 'hardware_bridge'), 'fault': ('ros2', 'hardware_bridge')}
ALL_READINESS_CHECKS = ('ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'scene_runtime_service', 'grasp_runtime_service', 'hardware_bridge', 'calibration', 'profiles', 'camera_alive', 'perception_alive', 'target_available')
PUBLIC_COMMAND_NAMES = ('startTask', 'stopTask', 'jog', 'servoCartesian', 'gripper', 'home', 'resetFault', 'recover')
COMMAND_REQUIRED_BY_NAME = {'startTask': ('ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'scene_runtime_service', 'grasp_runtime_service', 'hardware_bridge', 'camera_alive', 'perception_alive', 'target_available', 'calibration', 'profiles'), 'stopTask': (), 'jog': ('ros2', 'task_orchestrator', 'hardware_bridge'), 'servoCartesian': ('ros2', 'task_orchestrator', 'hardware_bridge'), 'gripper': ('ros2', 'task_orchestrator', 'hardware_bridge'), 'home': ('ros2', 'hardware_bridge'), 'resetFault': ('ros2', 'hardware_bridge'), 'recover': ('ros2', 'task_orchestrator', 'hardware_bridge')}
COMMAND_ALLOWED_MODES = {'startTask': ('idle', 'task'), 'stopTask': ('task', 'manual', 'maintenance', 'safe_stop', 'fault'), 'jog': ('manual', 'maintenance'), 'servoCartesian': ('manual', 'maintenance'), 'gripper': ('manual', 'maintenance'), 'home': ('idle', 'manual', 'maintenance', 'task', 'fault'), 'resetFault': ('fault', 'safe_stop'), 'recover': ('idle', 'maintenance', 'fault', 'safe_stop')}
HARDWARE_AUTHORITY_FIELDS = ('sourceStm32Online', 'sourceStm32Authoritative', 'sourceStm32TransportMode', 'sourceStm32Controllable', 'sourceStm32Simulated', 'sourceStm32SimulatedFallback')
SYSTEM_SEMANTIC_FIELDS = ('controllerMode', 'runtimePhase', 'taskStage')
COMPATIBILITY_ALIASES = {'mode': 'runtimePhase', 'operatorMode': 'controllerMode', 'currentStage': 'taskStage', 'allReady': 'modeReady'}
OFFICIAL_RUNTIME_LANES = ('sim_preview', 'sim_perception_preview', 'real_preview', 'hybrid_preview', 'hw_preview', 'full_demo_preview', 'sim_authoritative', 'full_demo_authoritative')
EXPERIMENTAL_RUNTIME_LANES = ('live_proto', 'live_control', 'real_validated_live')
RUNTIME_LANE_CLASSIFICATION = {'sim_preview': 'official_active', 'sim_perception_preview': 'official_active', 'real_preview': 'official_active', 'hybrid_preview': 'official_active', 'hw_preview': 'official_active', 'full_demo_preview': 'official_active', 'sim_authoritative': 'official_active', 'full_demo_authoritative': 'official_active', 'live_proto': 'experimental', 'live_control': 'experimental', 'real_validated_live': 'experimental'}
PRODUCT_LINE_CAPABILITIES = {'preview': {'label': 'Preview / Contract Only', 'description': '仅用于能力验证、链路联调与只读工作台。', 'taskWorkbenchVisible': False, 'taskExecutionInteractive': False, 'runtimeBadge': 'PREVIEW', 'promotionControlled': False, 'promotionEffective': False, 'promotionMissing': [], 'releaseChannel': 'official_active', 'lanes': ['full_demo_preview', 'hw_preview', 'hybrid_preview', 'real_preview', 'sim_perception_preview', 'sim_preview']}, 'validated_sim': {'label': 'Validated Simulation', 'description': '已验证仿真 authoritative lane，可进入正式任务工作台。', 'taskWorkbenchVisible': True, 'taskExecutionInteractive': True, 'runtimeBadge': 'VALIDATED_SIM', 'promotionControlled': False, 'promotionEffective': True, 'promotionMissing': [], 'releaseChannel': 'official_active', 'lanes': ['full_demo_authoritative', 'sim_authoritative']}, 'validated_live': {'label': 'Validated Live Hardware', 'description': '仅当 validated_live backbone、target-runtime gate、HIL gate 与 release checklist 全部通过时，才开放真机任务工作台。', 'taskWorkbenchVisible': False, 'taskExecutionInteractive': False, 'runtimeBadge': 'VALIDATED_LIVE', 'promotionControlled': True, 'promotionEffective': False, 'promotionMissing': ['validated_live_backbone_declared', 'target_runtime_gate_passed', 'hil_gate_passed', 'release_checklist_signed'], 'releaseChannel': 'experimental', 'lanes': []}}
TASK_CAPABILITY_TEMPLATES = [{'id': 'pick-red', 'name': '抓取红色目标', 'taskType': 'pick_place', 'backendTaskType': 'PICK_AND_PLACE', 'description': '单目标抓取并放置到红色料区。', 'defaultTargetCategory': 'red', 'allowedTargetCategories': ['red'], 'resolvedPlaceProfiles': {'red': 'bin_red'}, 'riskLevel': 'low', 'requiredRuntimeTier': 'validated_sim', 'taskProfilePath': 'task_pick_by_color.yaml', 'operatorHint': '适合单目标验证链路与基础抓取验收。', 'capabilityTags': ['pick', 'single_target', 'color:red'], 'preconditions': ['readiness.target_available', 'readiness.motion_planner', 'readiness.hardware_bridge'], 'sequenceMode': 'single_target', 'pluginKey': 'single_target', 'graphKey': 'pick-red', 'taskGraph': {'graphKey': 'pick-red', 'entryNode': 'perception', 'sequenceMode': 'single_target', 'pluginKey': 'single_target', 'preconditions': ['readiness.target_available', 'readiness.motion_planner', 'readiness.hardware_bridge'], 'nodes': [{'id': 'perception', 'kind': 'perception', 'stage': 'perception', 'label': '目标确认', 'terminal': False}, {'id': 'plan', 'kind': 'planning', 'stage': 'planning', 'label': '轨迹规划', 'terminal': False}, {'id': 'execute', 'kind': 'execution', 'stage': 'execution', 'label': '执行', 'terminal': False}, {'id': 'verify', 'kind': 'verification', 'stage': 'verification', 'label': '结果校验', 'terminal': True}], 'edges': [{'from': 'perception', 'to': 'plan', 'condition': 'target_locked'}, {'from': 'plan', 'to': 'execute', 'condition': 'plan_ready'}, {'from': 'execute', 'to': 'verify', 'condition': 'execution_done'}], 'recoveryPolicy': {'mode': 'retry_once_then_fail_closed', 'maxAutomaticRetry': 1, 'maxRetries': 2}, 'recovery': {'mode': 'retry_once_then_fail_closed', 'maxAutomaticRetry': 1, 'maxRetries': 2}, 'auditSurface': ['perception', 'plan', 'execute', 'verify'], 'graphVersion': 'v1', 'templateId': 'pick-red'}}, {'id': 'pick-blue', 'name': '抓取蓝色目标', 'taskType': 'pick_place', 'backendTaskType': 'PICK_AND_PLACE', 'description': '单目标抓取并放置到蓝色料区。', 'defaultTargetCategory': 'blue', 'allowedTargetCategories': ['blue'], 'resolvedPlaceProfiles': {'blue': 'bin_blue'}, 'riskLevel': 'low', 'requiredRuntimeTier': 'validated_sim', 'taskProfilePath': 'task_pick_by_color.yaml', 'operatorHint': '适合单目标验证链路与基础抓取验收。', 'capabilityTags': ['pick', 'single_target', 'color:blue'], 'preconditions': ['readiness.target_available', 'readiness.motion_planner', 'readiness.hardware_bridge'], 'sequenceMode': 'single_target', 'pluginKey': 'single_target', 'graphKey': 'pick-blue', 'taskGraph': {'graphKey': 'pick-blue', 'entryNode': 'perception', 'sequenceMode': 'single_target', 'pluginKey': 'single_target', 'preconditions': ['readiness.target_available', 'readiness.motion_planner', 'readiness.hardware_bridge'], 'nodes': [{'id': 'perception', 'kind': 'perception', 'stage': 'perception', 'label': '目标确认', 'terminal': False}, {'id': 'plan', 'kind': 'planning', 'stage': 'planning', 'label': '轨迹规划', 'terminal': False}, {'id': 'execute', 'kind': 'execution', 'stage': 'execution', 'label': '执行', 'terminal': False}, {'id': 'verify', 'kind': 'verification', 'stage': 'verification', 'label': '结果校验', 'terminal': True}], 'edges': [{'from': 'perception', 'to': 'plan', 'condition': 'target_locked'}, {'from': 'plan', 'to': 'execute', 'condition': 'plan_ready'}, {'from': 'execute', 'to': 'verify', 'condition': 'execution_done'}], 'recoveryPolicy': {'mode': 'retry_once_then_fail_closed', 'maxAutomaticRetry': 1, 'maxRetries': 2}, 'recovery': {'mode': 'retry_once_then_fail_closed', 'maxAutomaticRetry': 1, 'maxRetries': 2}, 'auditSurface': ['perception', 'plan', 'execute', 'verify'], 'graphVersion': 'v1', 'templateId': 'pick-blue'}}, {'id': 'pick-green', 'name': '抓取绿色目标', 'taskType': 'pick_place', 'backendTaskType': 'PICK_AND_PLACE', 'description': '单目标抓取并放置到绿色料区。', 'defaultTargetCategory': 'green', 'allowedTargetCategories': ['green'], 'resolvedPlaceProfiles': {'green': 'bin_green'}, 'riskLevel': 'low', 'requiredRuntimeTier': 'validated_sim', 'taskProfilePath': 'task_pick_by_color.yaml', 'operatorHint': '适合绿色类目标的单目标搬运验收。', 'capabilityTags': ['pick', 'single_target', 'color:green'], 'preconditions': ['readiness.target_available', 'readiness.motion_planner', 'readiness.hardware_bridge'], 'sequenceMode': 'single_target', 'pluginKey': 'single_target', 'graphKey': 'pick-green', 'taskGraph': {'graphKey': 'pick-green', 'entryNode': 'perception', 'sequenceMode': 'single_target', 'pluginKey': 'single_target', 'preconditions': ['readiness.target_available', 'readiness.motion_planner', 'readiness.hardware_bridge'], 'nodes': [{'id': 'perception', 'kind': 'perception', 'stage': 'perception', 'label': '目标确认', 'terminal': False}, {'id': 'plan', 'kind': 'planning', 'stage': 'planning', 'label': '轨迹规划', 'terminal': False}, {'id': 'execute', 'kind': 'execution', 'stage': 'execution', 'label': '执行', 'terminal': False}, {'id': 'verify', 'kind': 'verification', 'stage': 'verification', 'label': '结果校验', 'terminal': True}], 'edges': [{'from': 'perception', 'to': 'plan', 'condition': 'target_locked'}, {'from': 'plan', 'to': 'execute', 'condition': 'plan_ready'}, {'from': 'execute', 'to': 'verify', 'condition': 'execution_done'}], 'recoveryPolicy': {'mode': 'retry_once_then_fail_closed', 'maxAutomaticRetry': 1, 'maxRetries': 2}, 'recovery': {'mode': 'retry_once_then_fail_closed', 'maxAutomaticRetry': 1, 'maxRetries': 2}, 'auditSurface': ['perception', 'plan', 'execute', 'verify'], 'graphVersion': 'v1', 'templateId': 'pick-green'}}, {'id': 'sort-color', 'name': '按颜色分拣', 'taskType': 'sort_by_color', 'backendTaskType': 'PICK_BY_COLOR', 'description': '按颜色选择器进行分拣，红/蓝/绿目标分别落入对应料区。', 'defaultTargetCategory': 'red', 'allowedTargetCategories': ['red', 'blue', 'green'], 'resolvedPlaceProfiles': {'red': 'bin_red', 'blue': 'bin_blue', 'green': 'bin_green'}, 'riskLevel': 'medium', 'requiredRuntimeTier': 'validated_sim', 'taskProfilePath': 'task_pick_by_color.yaml', 'operatorHint': '需要颜色目标检测链路稳定。', 'capabilityTags': ['sort', 'color', 'multi_selector'], 'preconditions': ['readiness.target_available', 'readiness.motion_planner', 'readiness.hardware_bridge', 'readiness.perception_alive'], 'sequenceMode': 'selector_routed', 'pluginKey': 'selector_routed', 'graphKey': 'sort-color', 'taskGraph': {'graphKey': 'sort-color', 'entryNode': 'perception', 'sequenceMode': 'selector_routed', 'pluginKey': 'selector_routed', 'preconditions': ['readiness.target_available', 'readiness.motion_planner', 'readiness.hardware_bridge', 'readiness.perception_alive'], 'nodes': [{'id': 'perception', 'kind': 'perception', 'stage': 'perception', 'label': '目标确认', 'terminal': False}, {'id': 'selector', 'kind': 'selection', 'stage': 'selection', 'label': '目标类别路由', 'terminal': False}, {'id': 'plan', 'kind': 'planning', 'stage': 'planning', 'label': '轨迹规划', 'terminal': False}, {'id': 'execute', 'kind': 'execution', 'stage': 'execution', 'label': '执行', 'terminal': False}, {'id': 'verify', 'kind': 'verification', 'stage': 'verification', 'label': '结果校验', 'terminal': True}], 'edges': [{'from': 'perception', 'to': 'selector', 'condition': 'target_locked'}, {'from': 'selector', 'to': 'plan', 'condition': 'selector_resolved'}, {'from': 'plan', 'to': 'execute', 'condition': 'plan_ready'}, {'from': 'execute', 'to': 'verify', 'condition': 'execution_done'}], 'recoveryPolicy': {'mode': 'selector_retarget_then_fail_closed', 'maxAutomaticRetry': 1, 'maxRetries': 2}, 'recovery': {'mode': 'selector_retarget_then_fail_closed', 'maxAutomaticRetry': 1, 'maxRetries': 2}, 'auditSurface': ['perception', 'plan', 'execute', 'verify'], 'graphVersion': 'v1', 'templateId': 'sort-color'}}, {'id': 'sort-qr', 'name': '二维码识别搬运', 'taskType': 'sort_by_qr', 'backendTaskType': 'PICK_BY_QR', 'description': '根据二维码选择目标，当前统一落到默认料区，不宣称多料区二维码分拣能力。', 'defaultTargetCategory': 'qr_a', 'allowedTargetCategories': ['qr_a', 'qr_b', 'qr_c'], 'resolvedPlaceProfiles': {'qr_a': 'default', 'qr_b': 'default', 'qr_c': 'default'}, 'riskLevel': 'medium', 'requiredRuntimeTier': 'validated_sim', 'taskProfilePath': 'task_pick_by_color.yaml', 'operatorHint': '当前二维码任务仅保证识别触发与默认料区搬运语义。', 'capabilityTags': ['sort', 'qr', 'multi_selector'], 'preconditions': ['readiness.target_available', 'readiness.motion_planner', 'readiness.hardware_bridge', 'readiness.perception_alive'], 'sequenceMode': 'selector_routed', 'pluginKey': 'selector_routed', 'graphKey': 'sort-qr', 'taskGraph': {'graphKey': 'sort-qr', 'entryNode': 'perception', 'sequenceMode': 'selector_routed', 'pluginKey': 'selector_routed', 'preconditions': ['readiness.target_available', 'readiness.motion_planner', 'readiness.hardware_bridge', 'readiness.perception_alive'], 'nodes': [{'id': 'perception', 'kind': 'perception', 'stage': 'perception', 'label': '目标确认', 'terminal': False}, {'id': 'selector', 'kind': 'selection', 'stage': 'selection', 'label': '目标类别路由', 'terminal': False}, {'id': 'plan', 'kind': 'planning', 'stage': 'planning', 'label': '轨迹规划', 'terminal': False}, {'id': 'execute', 'kind': 'execution', 'stage': 'execution', 'label': '执行', 'terminal': False}, {'id': 'verify', 'kind': 'verification', 'stage': 'verification', 'label': '结果校验', 'terminal': True}], 'edges': [{'from': 'perception', 'to': 'selector', 'condition': 'target_locked'}, {'from': 'selector', 'to': 'plan', 'condition': 'selector_resolved'}, {'from': 'plan', 'to': 'execute', 'condition': 'plan_ready'}, {'from': 'execute', 'to': 'verify', 'condition': 'execution_done'}], 'recoveryPolicy': {'mode': 'selector_retarget_then_fail_closed', 'maxAutomaticRetry': 1, 'maxRetries': 2}, 'recovery': {'mode': 'selector_retarget_then_fail_closed', 'maxAutomaticRetry': 1, 'maxRetries': 2}, 'auditSurface': ['perception', 'plan', 'execute', 'verify'], 'graphVersion': 'v1', 'templateId': 'sort-qr'}}, {'id': 'clear-table', 'name': '清台任务', 'taskType': 'clear_table', 'backendTaskType': 'CLEAR_TABLE', 'description': '持续抓取当前工作台上全部可执行目标并放置到默认料区。', 'defaultTargetCategory': None, 'allowedTargetCategories': [], 'resolvedPlaceProfiles': {'default': 'default'}, 'riskLevel': 'high', 'requiredRuntimeTier': 'validated_sim', 'taskProfilePath': 'task_clear_table.yaml', 'operatorHint': '连续搬运任务，对感知、规划与执行链路稳定性要求更高。', 'capabilityTags': ['clear_table', 'continuous', 'multi_target'], 'preconditions': ['readiness.motion_planner', 'readiness.hardware_bridge', 'readiness.perception_alive'], 'sequenceMode': 'continuous', 'pluginKey': 'continuous', 'graphKey': 'clear-table', 'taskGraph': {'graphKey': 'clear-table', 'entryNode': 'perception', 'sequenceMode': 'continuous', 'pluginKey': 'continuous', 'preconditions': ['readiness.motion_planner', 'readiness.hardware_bridge', 'readiness.perception_alive'], 'nodes': [{'id': 'perception', 'kind': 'perception', 'stage': 'perception', 'label': '目标扫描', 'terminal': False}, {'id': 'plan', 'kind': 'planning', 'stage': 'planning', 'label': '批次规划', 'terminal': False}, {'id': 'execute_batch', 'kind': 'execution', 'stage': 'execution', 'label': '批次执行', 'terminal': False}, {'id': 'verify_batch', 'kind': 'verification', 'stage': 'verification', 'label': '批次校验', 'terminal': False}, {'id': 'complete', 'kind': 'terminal', 'stage': 'terminal', 'label': '完成', 'terminal': True}], 'edges': [{'from': 'perception', 'to': 'plan', 'condition': 'next_target_available'}, {'from': 'plan', 'to': 'execute_batch', 'condition': 'plan_ready'}, {'from': 'execute_batch', 'to': 'verify_batch', 'condition': 'execution_done'}, {'from': 'verify_batch', 'to': 'perception', 'condition': 'targets_remaining'}, {'from': 'verify_batch', 'to': 'complete', 'condition': 'workspace_clear'}], 'recoveryPolicy': {'mode': 'batch_continue_with_failure_ledger', 'maxAutomaticRetry': 1, 'maxRetries': 2}, 'recovery': {'mode': 'batch_continue_with_failure_ledger', 'maxAutomaticRetry': 1, 'maxRetries': 2}, 'auditSurface': ['perception', 'plan', 'execute', 'verify'], 'graphVersion': 'v1', 'templateId': 'clear-table'}}]

def required_checks_for_mode(mode: str) -> tuple[str, ...]:
    normalized = str(mode or "").strip().lower()
    return READINESS_REQUIRED_BY_MODE.get(normalized, READINESS_REQUIRED_BY_MODE['task'])

def _command_policy(allowed: bool, reason: str) -> dict[str, Any]:
    return {'allowed': bool(allowed), 'reason': str(reason)}

def _effective_check_ok(checks: dict[str, Any], name: str) -> bool:
    payload = checks.get(name, {})
    return bool(payload.get('effectiveOk', payload.get('ok', False)))

def _missing_required_checks(checks: dict[str, dict[str, Any]], names: Iterable[str]) -> list[str]:
    return [name for name in names if not _effective_check_ok(checks, name)]

def _missing_reason(checks: dict[str, dict[str, Any]], missing: list[str], default_reason: str) -> str:
    if not missing:
        return default_reason
    detailed: list[str] = []
    for name in missing:
        payload = checks.get(name, {})
        detail = str(payload.get('detail', '') or '').strip()
        detailed.append(f'{name}({detail})' if detail else name)
    return 'missing readiness: ' + ', '.join(detailed)

def build_command_policies(mode: str, checks: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized_mode = str(mode or '').strip().lower() or 'boot'
    start_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['startTask'])
    manual_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['jog'])
    home_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['home'])
    reset_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['resetFault'])
    recover_missing = _missing_required_checks(checks, COMMAND_REQUIRED_BY_NAME['recover'])

    start_allowed = normalized_mode in COMMAND_ALLOWED_MODES['startTask'] and not start_missing
    manual_ready = normalized_mode in COMMAND_ALLOWED_MODES['jog'] and not manual_missing
    stop_allowed = normalized_mode in COMMAND_ALLOWED_MODES['stopTask']
    hardware_fault = bool(checks.get('hardware_bridge', {}).get('detail') in {'fault', 'hardware_blocked', 'hardware_fault'})
    home_allowed = normalized_mode in COMMAND_ALLOWED_MODES['home'] and not home_missing and not hardware_fault
    reset_allowed = normalized_mode in COMMAND_ALLOWED_MODES['resetFault'] and not reset_missing
    recover_allowed = normalized_mode in COMMAND_ALLOWED_MODES['recover'] and not recover_missing

    if start_allowed:
        start_reason = 'ready'
    elif start_missing:
        start_reason = _missing_reason(checks, start_missing, 'task execution requires authoritative runtime lane')
    else:
        start_reason = f'mode {normalized_mode} does not allow task start'

    manual_reason = 'ready' if manual_ready else (_missing_reason(checks, manual_missing, 'manual operations require manual or maintenance mode') if manual_missing else 'manual operations require manual or maintenance mode')

    if home_allowed:
        home_reason = 'ready'
    elif hardware_fault:
        home_reason = 'home blocked by hardware fault'
    elif normalized_mode not in COMMAND_ALLOWED_MODES['home']:
        home_reason = 'home blocked by current runtime mode'
    else:
        home_reason = _missing_reason(checks, home_missing, 'missing readiness: hardware_bridge')

    if reset_allowed:
        reset_reason = 'ready'
    elif reset_missing:
        reset_reason = _missing_reason(checks, reset_missing, 'reset fault requires authoritative hardware bridge')
    else:
        reset_reason = 'reset fault only valid in fault or safe-stop mode'

    if recover_allowed:
        recover_reason = 'ready'
    elif recover_missing:
        recover_reason = _missing_reason(checks, recover_missing, 'recover requires authoritative runtime control path')
    else:
        recover_reason = 'recover only valid in idle / maintenance / fault / safe-stop mode'

    return {
        'startTask': _command_policy(start_allowed, start_reason),
        'stopTask': _command_policy(stop_allowed, 'ready' if stop_allowed else 'no active runtime command path'),
        'jog': _command_policy(manual_ready, manual_reason),
        'servoCartesian': _command_policy(manual_ready, manual_reason),
        'gripper': _command_policy(manual_ready, manual_reason),
        'home': _command_policy(home_allowed, home_reason),
        'resetFault': _command_policy(reset_allowed, reset_reason),
        'recover': _command_policy(recover_allowed, recover_reason),
    }

def build_readiness_layers(mode: str, checks: dict[str, dict[str, Any]]) -> tuple[bool, bool]:
    runtime_healthy = all(bool(checks.get(name, {}).get('effectiveOk', checks.get(name, {}).get('ok', False))) for name in RUNTIME_HEALTH_REQUIRED)
    required = required_checks_for_mode(mode)
    mode_ready = bool(required) and all(bool(checks.get(name, {}).get('effectiveOk', checks.get(name, {}).get('ok', False))) for name in required)
    return runtime_healthy, mode_ready
