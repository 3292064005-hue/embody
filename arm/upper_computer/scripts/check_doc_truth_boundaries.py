#!/usr/bin/env python3
from __future__ import annotations

"""Check documentation truth-source boundaries.

The repository keeps current runtime truth in canonical architecture documents,
while generated mirrors and archive material are not allowed to silently look like
fresh source-of-truth documents. This script is warning-only by default and can be
made blocking with ``--strict`` for release hardening.
"""

import argparse
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
GENERATED_MARKERS = (
    'generated',
    'do not edit',
    'auto-generated',
    'mirrored from',
)
ARCHIVE_CURRENT_FACT_PATTERNS = (
    'canonical runtime truth',
    'current runtime truth',
    'authoritative current runtime',
)


def _iter_markdown_files(path: Path) -> Iterable[Path]:
    if not path.exists():
        return ()
    return sorted(item for item in path.rglob('*.md') if item.is_file())


def check_generated_docs() -> list[str]:
    """Return warnings for generated docs without an explicit generator marker.

    Args:
        None.

    Returns:
        list[str]: Human-readable warning messages.

    Raises:
        Does not raise.

    Boundary behavior:
        The check is conservative and only inspects markdown files under
        ``docs/generated``. Non-markdown generated artifacts are ignored.
    """
    warnings: list[str] = []
    for path in _iter_markdown_files(DOCS / 'generated'):
        head = path.read_text(encoding='utf-8', errors='ignore')[:2048].lower()
        if not any(marker in head for marker in GENERATED_MARKERS):
            warnings.append(f'{path.relative_to(ROOT)} lacks a generated-document marker')
    return warnings


def check_archive_docs() -> list[str]:
    """Return warnings for archive docs that assert current authority.

    Args:
        None.

    Returns:
        list[str]: Human-readable warning messages.

    Raises:
        Does not raise.

    Boundary behavior:
        Archive documents may describe historical facts, but phrases that assert
        current canonical authority are flagged for review.
    """
    warnings: list[str] = []
    for path in _iter_markdown_files(DOCS / 'archive'):
        text = path.read_text(encoding='utf-8', errors='ignore').lower()
        for pattern in ARCHIVE_CURRENT_FACT_PATTERNS:
            if pattern in text:
                warnings.append(f'{path.relative_to(ROOT)} contains current-authority phrase: {pattern}')
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description='Check docs generated/archive truth boundaries.')
    parser.add_argument('--strict', action='store_true', help='treat warnings as blocking failures')
    args = parser.parse_args()
    warnings = [*check_generated_docs(), *check_archive_docs()]
    for warning in warnings:
        print(f'DOC_BOUNDARY_WARNING: {warning}')
    if warnings and args.strict:
        return 1
    print(f'DOC_BOUNDARY_SUMMARY: warnings={len(warnings)} strict={args.strict}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
