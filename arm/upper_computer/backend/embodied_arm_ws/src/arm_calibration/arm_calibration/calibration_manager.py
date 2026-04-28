from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from .transform_utils import CalibrationModel


@dataclass
class CalibrationManager:
    active_profile: str = 'default'
    model: CalibrationModel = field(default_factory=CalibrationModel)

    def load_from_dict(self, cfg: Dict[str, Any]) -> CalibrationModel:
        self.model = CalibrationModel.from_config(cfg)
        self.active_profile = str(cfg.get('version', self.active_profile))
        return self.model

    def load_from_path(self, path: str | Path) -> CalibrationModel:
        import yaml
        data = yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}
        return self.load_from_dict(data)

    def export(self) -> Dict[str, Any]:
        return self.model.to_dict()
