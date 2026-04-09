from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkspaceMapper:
    x_bias: float = 0.0
    y_bias: float = 0.0

    def project_pixel_to_world(self, u: float, v: float) -> dict:
        return {'x': float(u) + self.x_bias, 'y': float(v) + self.y_bias}
