try:
    from .diagnostics_summary_node import DiagnosticsSummaryNode as DiagnosticsNode, main
except Exception:
    class DiagnosticsNode:  # pragma: no cover
        node_name = 'diagnostics_node'
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
    def main(args=None):
        _ = args

__all__ = ['DiagnosticsNode', 'main']
