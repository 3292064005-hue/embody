from __future__ import annotations

"""ROS ingress registration for the gateway runtime bridge."""

from typing import Any


def bind_runtime_ingress(node: Any) -> None:
    """Bind all gateway ROS subscriptions on a node instance.

    Args:
        node: Gateway ROS node exposing `create_subscription`, message types,
            topic names, and bound callback methods.

    Returns:
        None.

    Raises:
        AttributeError: Propagated if the supplied node is missing required
            subscription callbacks or ROS message definitions.

    Boundary behavior:
        Optional typed shadow subscriptions are registered only when the related
        message type is available in the current environment.
    """
    node.create_subscription(node.SystemState, node.TopicNames.SYSTEM_STATE, node._on_system_state, 20)
    node.create_subscription(node.HardwareState, node.TopicNames.HARDWARE_STATE, node._on_hardware_state, 20)
    node.create_subscription(node.TargetInfo, node.TopicNames.VISION_TARGET, node._on_target, 20)
    node.create_subscription(node.String, node.TopicNames.VISION_TARGETS, node._on_targets_summary, 20)
    if node.TargetArray is not object:
        node.create_subscription(node.TargetArray, node.TopicNames.VISION_TARGETS_TYPED, node._on_targets_summary_typed, 20)
    node.create_subscription(node.TaskEvent, node.TopicNames.LOG_EVENT, node._on_log_event, 50)
    node.create_subscription(node.String, node.TopicNames.TASK_STATUS, node._on_task_status, 20)
    if node.TaskStatus is not object:
        node.create_subscription(node.TaskStatus, node.TopicNames.TASK_STATUS_TYPED, node._on_task_status_typed, 20)
    node.create_subscription(node.String, node.TopicNames.DIAGNOSTICS_HEALTH, node._on_diagnostics_health, 20)
    if node.DiagnosticsSummary is not object:
        node.create_subscription(node.DiagnosticsSummary, node.TopicNames.DIAGNOSTICS_SUMMARY_TYPED, node._on_diagnostics_summary_typed, 20)
    node.create_subscription(node.String, node.TopicNames.CALIBRATION_PROFILE, node._on_calibration_profile, 10)
    if node.CalibrationProfileMsg is not object:
        node.create_subscription(node.CalibrationProfileMsg, node.TopicNames.CALIBRATION_PROFILE_TYPED, node._on_calibration_profile_typed, 10)
    node.create_subscription(node.String, node.TopicNames.READINESS_STATE, node._on_readiness_state, 10)
    if node.ReadinessState is not object:
        node.create_subscription(node.ReadinessState, node.TopicNames.READINESS_STATE_TYPED, node._on_readiness_state_typed, 10)
