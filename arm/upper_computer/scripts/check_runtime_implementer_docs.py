#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DOC_INDEX = ROOT / 'docs' / 'INDEX.md'
SYSTEM_OVERVIEW = ROOT / 'docs' / 'architecture' / 'system-overview.md'
COMMAND_LIFECYCLE_DOC = ROOT / 'docs' / 'architecture' / 'command-lifecycle-and-state-ownership.md'
AUTHORITY_SECTIONS_DOC = ROOT / 'docs' / 'architecture' / 'runtime-authority-section-projections.md'
API_CONTRACT = ROOT / 'docs' / 'interfaces' / 'api-contract.md'
TERMS = ROOT / 'docs' / 'architecture' / 'terms-and-reference-blocks.md'

REQUIRED_REFERENCES = {
    DOC_INDEX: [
        'command-lifecycle-and-state-ownership.md',
        'runtime-authority-section-projections.md',
    ],
    SYSTEM_OVERVIEW: [
        'command-lifecycle-and-state-ownership.md',
        'runtime-authority-section-projections.md',
    ],
    COMMAND_LIFECYCLE_DOC: ['accepted', 'success', 'failed', 'blocked', 'rejected', 'observed'],
    AUTHORITY_SECTIONS_DOC: ['runtime_authority_sections', 'product_lines.yaml', 'command_planes.yaml', 'capability_registry.yaml', 'task_catalog_contract.yaml', 'runtime_governance.yaml'],
    API_CONTRACT: ['accepted', 'success', 'observed', 'rejected'],
    TERMS: ['accepted', 'success', 'observed', 'rejected'],
}


def main() -> int:
    issues: list[str] = []
    for path, required_tokens in REQUIRED_REFERENCES.items():
        if not path.exists():
            issues.append(f'missing required implementer doc: {path.relative_to(ROOT).as_posix()}')
            continue
        text = path.read_text(encoding='utf-8')
        for token in required_tokens:
            if token not in text:
                issues.append(f'{path.relative_to(ROOT).as_posix()} missing required token: {token}')
    if issues:
        for issue in issues:
            print(issue)
        return 1
    print('runtime implementer docs aligned')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
