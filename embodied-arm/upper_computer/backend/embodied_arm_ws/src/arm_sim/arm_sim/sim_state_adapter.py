class SimStateAdapter:
    def to_hardware_state(self, *, busy: bool = False) -> dict:
        return {'busy': busy, 'mode': 'sim'}
