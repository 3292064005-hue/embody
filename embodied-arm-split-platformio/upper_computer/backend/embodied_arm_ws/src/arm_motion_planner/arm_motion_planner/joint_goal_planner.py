class JointGoalPlanner:
    def build_request(self, joints: dict) -> dict:
        return {'goal_type': 'joint', 'joints': joints}
