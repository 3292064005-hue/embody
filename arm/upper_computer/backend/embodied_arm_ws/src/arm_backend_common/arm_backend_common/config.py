from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml

@dataclass
class LoadedConfig:
    path: Path
    data: Dict[str, Any]

def load_yaml(path: str | Path) -> LoadedConfig:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Config not found: {file_path}")
    with file_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {file_path}")
    return LoadedConfig(path=file_path, data=data)

def require_keys(data: Dict[str, Any], keys: list[str], scope: str = "config") -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise KeyError(f"Missing keys in {scope}: {missing}")
