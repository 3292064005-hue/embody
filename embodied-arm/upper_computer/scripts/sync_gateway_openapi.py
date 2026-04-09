#!/usr/bin/env python3
from __future__ import annotations

"""Synchronize gateway/openapi/runtime_api.yaml from the assembled FastAPI app."""

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gateway.server import app

OPENAPI_PATH = ROOT / 'gateway' / 'openapi' / 'runtime_api.yaml'
HEADER = '# Generated from gateway.server:create_app(). Do not edit manually.\n'


def _render() -> str:
    schema = app.openapi()
    return HEADER + yaml.safe_dump(schema, sort_keys=False, allow_unicode=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail instead of writing when the spec is out of sync.')
    args = parser.parse_args()

    rendered = _render()
    current = OPENAPI_PATH.read_text(encoding='utf-8') if OPENAPI_PATH.exists() else ''
    if current == rendered:
        print('[gateway-openapi] already in sync')
        return 0
    if args.check:
        print('[gateway-openapi] drift detected: runtime_api.yaml')
        return 1
    OPENAPI_PATH.write_text(rendered, encoding='utf-8')
    print('[gateway-openapi] updated: runtime_api.yaml')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
