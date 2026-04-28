try:
    from .calibration_manager_node import CalibrationManagerNode as CalibrationNode, main
except Exception:
    class CalibrationNode:  # pragma: no cover
        node_name = 'calibration_node'
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
    def main(args=None):
        _ = args

__all__ = ['CalibrationNode', 'main']
