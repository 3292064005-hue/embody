class CartesianSegmentPlanner:
    def build_request(self, waypoints: list[dict]) -> dict:
        return {'goal_type': 'cartesian', 'waypoints': waypoints}
