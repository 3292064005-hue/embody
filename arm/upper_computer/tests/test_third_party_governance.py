from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_root_governance_artifacts_exist() -> None:
    for relative in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'third_party/UPSTREAM_INDEX.md'):
        path = ROOT / relative
        assert path.exists(), relative
        assert path.read_text(encoding='utf-8').strip()
