from arm_hardware_bridge import HardwareBridgeNode, CommandRouter, StateAggregator, ModeManager, HeartbeatMonitor


def test_hardware_bridge_blueprint_facades_exist_and_behave():
    assert HardwareBridgeNode is not None
    assert CommandRouter().route({'kind': 'HOME'})['topic'] == '/arm/internal/hardware_cmd'
    assert StateAggregator().merge({'a': 1}, {'b': 2}) == {'a': 1, 'b': 2}
    manager = ModeManager('sim')
    assert manager.set_mode('real') == 'real'
    assert HeartbeatMonitor().stale(0.0, 2.0, 1.0)
