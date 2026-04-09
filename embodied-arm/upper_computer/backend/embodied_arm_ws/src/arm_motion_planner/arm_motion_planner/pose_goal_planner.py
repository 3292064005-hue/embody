class PoseGoalPlanner:
    def build_request(self, pose: dict) -> dict:
        return {'goal_type': 'pose', 'pose': pose}
