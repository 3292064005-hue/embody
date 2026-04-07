class StatusNotifier:
    def build_notice(self, state: str) -> dict:
        return {"state": state}
