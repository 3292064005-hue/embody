from __future__ import annotations

from pathlib import Path
import yaml


class TaskProfileLoader:
    def load(self, path: str) -> dict:
        return yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}
