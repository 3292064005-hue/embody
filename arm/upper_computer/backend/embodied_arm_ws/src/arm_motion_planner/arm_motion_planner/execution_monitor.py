class ExecutionMonitor:
    def summarize(self, result: dict) -> dict:
        return {'ok': bool(result)}
