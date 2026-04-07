from __future__ import annotations


class ModeManager:
    def __init__(self, mode: str = 'sim') -> None:
        self.mode = mode

    def set_mode(self, mode: str) -> str:
        self.mode = str(mode)
        return self.mode
