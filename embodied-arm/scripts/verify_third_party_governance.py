#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    ROOT / 'LICENSE',
    ROOT / 'THIRD_PARTY_NOTICES.md',
    ROOT / 'third_party' / 'UPSTREAM_INDEX.md',
]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    for path in REQUIRED:
        _require(path.exists(), f'missing governance artifact: {path.relative_to(ROOT)}')
        _require(path.read_text(encoding='utf-8').strip() != '', f'empty governance artifact: {path.relative_to(ROOT)}')
    inventory = {
        'license': 'LICENSE',
        'notices': 'THIRD_PARTY_NOTICES.md',
        'upstreamIndex': 'third_party/UPSTREAM_INDEX.md',
        'vendoredModules': [],
    }
    artifact = ROOT / 'artifacts' / 'third_party_audit' / 'inventory.json'
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'third-party governance verification passed -> {artifact}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f'third-party governance verification failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
