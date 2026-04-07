from arm_backend_common.enums import FaultCode, SystemMode
from arm_safety_supervisor import SafetyPolicy


def test_safety_policy_triggers_estop_and_readiness_loss():
    policy = SafetyPolicy()
    decision = policy.evaluate(system_mode=int(SystemMode.EXECUTE), hardware={'estop_pressed': True}, readiness={'allReady': True})
    assert decision.stop_requested
    assert decision.fault_code == FaultCode.ESTOP_TRIGGERED

    decision = policy.evaluate(system_mode=int(SystemMode.PLAN), hardware={'estop_pressed': False, 'limit_triggered': False, 'hardware_fault_code': 0}, readiness={'allReady': False, 'missingChecks': ['camera']})
    assert decision.stop_requested
    assert decision.event_type == 'READINESS_LOSS'
