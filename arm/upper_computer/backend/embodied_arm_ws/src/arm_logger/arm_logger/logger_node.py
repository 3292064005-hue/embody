try:
    from .event_logger_node import EventLoggerNode, main
except Exception:
    class EventLoggerNode:  # pragma: no cover
        node_name = 'event_logger'
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
    def main(args=None):
        _ = args

__all__ = ['EventLoggerNode', 'main']
