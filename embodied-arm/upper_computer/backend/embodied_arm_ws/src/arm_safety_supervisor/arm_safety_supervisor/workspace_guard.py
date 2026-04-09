from __future__ import annotations


class WorkspaceGuard:
    def within(self, x: float, y: float, radius: float) -> bool:
        return (x * x + y * y) <= radius * radius
