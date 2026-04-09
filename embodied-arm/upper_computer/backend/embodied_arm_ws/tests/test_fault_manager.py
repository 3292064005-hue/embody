from arm_backend_common.enums import FaultCode
from arm_task_orchestrator import FaultManager


def test_fault_manager_marks_retryable_faults_as_non_terminal():
    manager = FaultManager()
    decision = manager.classify(FaultCode.EXECUTE_TIMEOUT, 'timeout')
    assert decision.action == 'retry_or_fault'
    assert decision.terminal is False


def test_fault_manager_marks_non_retryable_faults_as_terminal():
    manager = FaultManager()
    decision = manager.classify(FaultCode.ESTOP_TRIGGERED, 'estop')
    assert decision.action == 'fault'
    assert decision.terminal is True
