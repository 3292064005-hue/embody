from __future__ import annotations

from pathlib import Path


class LogRotator:
    def rotate(self, root: str | Path, max_files: int = 10) -> list[str]:
        root = Path(root)
        files = sorted([p.name for p in root.glob('*')])
        return files[-max_files:]
