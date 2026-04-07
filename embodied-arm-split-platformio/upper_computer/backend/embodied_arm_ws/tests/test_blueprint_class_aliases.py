from arm_task_orchestrator.state_machine import TaskStateMachine
from arm_calibration.calibration_node import CalibrationNode
from arm_diagnostics.diagnostics_node import DiagnosticsNode
from arm_logger.logger_node import EventLoggerNode
from arm_hardware_bridge.hardware_bridge_node import HardwareBridgeNode


def test_blueprint_alias_classes_are_importable():
    assert TaskStateMachine is not None
    assert CalibrationNode is not None
    assert DiagnosticsNode is not None
    assert EventLoggerNode is not None
    assert HardwareBridgeNode is not None
