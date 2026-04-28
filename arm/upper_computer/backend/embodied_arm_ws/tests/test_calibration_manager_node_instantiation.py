from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

from arm_common import ServiceNames

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
_MISSING = object()
_STUBBED_MODULE_NAMES = (
    'rclpy',
    'rclpy.node',
    'rclpy.qos',
    'std_msgs',
    'std_msgs.msg',
    'std_srvs',
    'std_srvs.srv',
    'arm_calibration.calibration_manager_node',
)


def _snapshot_stubbed_modules():
    return {name: sys.modules.get(name, _MISSING) for name in _STUBBED_MODULE_NAMES}


def _restore_stubbed_modules(snapshot) -> None:
    for name, module in snapshot.items():
        if module is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


class _FakeParameterValue:
    def __init__(self, value):
        self.string_value = value if isinstance(value, str) else ''


class _FakeParameter:
    def __init__(self, value):
        self.value = value

    def get_parameter_value(self):
        return _FakeParameterValue(self.value)


class _FakeLogger:
    def info(self, *_args, **_kwargs):
        return None

    def warn(self, *_args, **_kwargs):
        return None


class _FakePublisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


class _FakeNode:
    def __init__(self, *_args, **_kwargs):
        self._parameters = {}
        self.services = []
        self.publishers = []

    def declare_parameter(self, name, value):
        self._parameters[name] = value

    def get_parameter(self, name):
        return _FakeParameter(self._parameters.get(name, ''))

    def create_publisher(self, *_args, **_kwargs):
        publisher = _FakePublisher()
        self.publishers.append(publisher)
        return publisher

    def create_service(self, srv_type, name, callback):
        self.services.append((srv_type, name, callback))
        return object()

    def create_timer(self, *_args, **_kwargs):
        return object()

    def get_logger(self):
        return _FakeLogger()


class _FakeQosProfile:
    def __init__(self, **_kwargs):
        pass


class _Trigger:
    class Request:
        pass

    class Response:
        def __init__(self):
            self.success = False
            self.message = ''


class _ActivateCalibrationVersion:
    class Request:
        def __init__(self):
            self.profile_id = ''

    class Response:
        def __init__(self):
            self.success = False
            self.message = ''
            self.profile_id = ''


class _String:
    def __init__(self, data=''):
        self.data = data


def _load_module():
    rclpy = types.ModuleType('rclpy')
    node_mod = types.ModuleType('rclpy.node')
    qos_mod = types.ModuleType('rclpy.qos')
    std_msgs = types.ModuleType('std_msgs')
    std_msgs_msg = types.ModuleType('std_msgs.msg')
    std_srvs = types.ModuleType('std_srvs')
    std_srvs_srv = types.ModuleType('std_srvs.srv')

    node_mod.Node = _FakeNode
    qos_mod.QoSProfile = _FakeQosProfile
    qos_mod.DurabilityPolicy = types.SimpleNamespace(TRANSIENT_LOCAL='TRANSIENT_LOCAL')
    qos_mod.HistoryPolicy = types.SimpleNamespace(KEEP_LAST='KEEP_LAST')
    qos_mod.ReliabilityPolicy = types.SimpleNamespace(RELIABLE='RELIABLE')
    std_msgs_msg.String = _String
    std_srvs_srv.Trigger = _Trigger

    sys.modules['rclpy'] = rclpy
    sys.modules['rclpy.node'] = node_mod
    sys.modules['rclpy.qos'] = qos_mod
    sys.modules['std_msgs'] = std_msgs
    sys.modules['std_msgs.msg'] = std_msgs_msg
    sys.modules['std_srvs'] = std_srvs
    sys.modules['std_srvs.srv'] = std_srvs_srv

    import arm_common

    arm_common.SrvTypes.ActivateCalibrationVersion = _ActivateCalibrationVersion

    sys.path.insert(0, str(SRC / 'arm_calibration'))
    if 'arm_calibration.calibration_manager_node' in sys.modules:
        del sys.modules['arm_calibration.calibration_manager_node']
    return importlib.import_module('arm_calibration.calibration_manager_node')


def test_calibration_manager_node_registers_activate_callback_without_missing_attribute():
    snapshot = _snapshot_stubbed_modules()
    try:
        module = _load_module()
        node = module.CalibrationManagerNode()
        service_names = [name for _srv_type, name, _callback in node.services]
        callbacks = {name: callback for _srv_type, name, callback in node.services}
        assert ServiceNames.ACTIVATE_CALIBRATION in service_names
        assert callable(callbacks[ServiceNames.ACTIVATE_CALIBRATION])
    finally:
        _restore_stubbed_modules(snapshot)


def test_calibration_manager_node_instantiates_even_if_lifecycle_support_loaded_before_ros_node_stub():
    import arm_backend_common.lifecycle_support as lifecycle_support

    snapshot = _snapshot_stubbed_modules()
    for name in _STUBBED_MODULE_NAMES:
        sys.modules.pop(name, None)
    try:
        importlib.reload(lifecycle_support)
        module = _load_module()
        node = module.CalibrationManagerNode()
        assert callable(node.get_logger)
        assert any(name == ServiceNames.ACTIVATE_CALIBRATION for _srv_type, name, _callback in node.services)
    finally:
        _restore_stubbed_modules(snapshot)
        importlib.reload(lifecycle_support)
