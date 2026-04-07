from __future__ import annotations

import json


class DashboardExporter:
    def export(self, payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False)
