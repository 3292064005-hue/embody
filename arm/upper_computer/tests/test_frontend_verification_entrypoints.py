from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_JSON = ROOT / 'frontend' / 'package.json'
VERIFY_REPOSITORY = ROOT / 'scripts' / 'verify_repository.py'
ENSURE_DEPS = ROOT / 'scripts' / 'ensure_frontend_deps.sh'
CI_WORKFLOW = ROOT / '.github' / 'workflows' / 'ci.yml'
MAKEFILE = ROOT / 'Makefile'


def test_frontend_verification_uses_installed_vue_tsc_bin_entrypoint() -> None:
    package_text = PACKAGE_JSON.read_text(encoding='utf-8')
    verify_text = VERIFY_REPOSITORY.read_text(encoding='utf-8')
    ensure_text = ENSURE_DEPS.read_text(encoding='utf-8')
    workflow_text = CI_WORKFLOW.read_text(encoding='utf-8')
    makefile_text = MAKEFILE.read_text(encoding='utf-8')

    expected_app = 'node ./node_modules/vue-tsc/bin/vue-tsc.js --noEmit -p tsconfig.app.json'
    expected_test = 'node ./node_modules/vue-tsc/bin/vue-tsc.js --noEmit -p tsconfig.vitest.json'
    assert expected_app in package_text
    assert expected_test in package_text
    assert "['npm', 'run', 'typecheck']" in verify_text
    assert "['npm', 'run', 'typecheck:test']" in verify_text
    assert 'node_modules/vue-tsc/bin/vue-tsc.js' in ensure_text
    assert 'node_modules/vue-tsc/index.js' not in package_text
    assert 'node_modules/vue-tsc/index.js' not in verify_text
    assert 'npm run typecheck:test' in workflow_text
    assert 'npm run typecheck:test' in makefile_text
    assert 'frontend-typecheck-test' in verify_text
