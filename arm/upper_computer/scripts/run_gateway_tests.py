#!/usr/bin/env python3
"""Run gateway pytest suite with a controlled subprocess environment.

This wrapper avoids shell-specific process handling differences in repository
verification runs and preserves deterministic write-bytecode disabling.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root_dir = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [sys.executable, "-m", "pytest", "-q", "gateway/tests", "-p", "no:cacheprovider"]
    completed = subprocess.run(cmd, cwd=root_dir, env=env)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
