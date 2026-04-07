try:
    from .hardware_state_aggregator_node import HardwareStateAggregatorNode as HardwareBridgeNode
except Exception:
    class HardwareBridgeNode:  # pragma: no cover - import-safe facade
        node_name = 'hardware_bridge'

        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

__all__ = ["HardwareBridgeNode"]
