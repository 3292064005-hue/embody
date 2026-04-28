from __future__ import annotations


class HandEyeOffsetSolver:
    def solve(self, observations) -> dict:
        _ = observations
        return {'x_bias': 0.0, 'y_bias': 0.0, 'yaw_bias': 0.0}
