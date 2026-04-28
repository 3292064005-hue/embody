from __future__ import annotations

import json
from pathlib import Path


class TaskRecordWriter:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, task_id: str, payload: dict) -> Path:
        path = self.root / f'{task_id}.json'
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return path
