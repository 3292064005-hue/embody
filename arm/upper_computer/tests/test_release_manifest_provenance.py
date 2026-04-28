from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_final_audit_module(repo_root: Path):
    sys.path.insert(0, str(repo_root / 'upper_computer'))
    sys.path.insert(0, str(repo_root / 'upper_computer' / 'scripts'))
    return _load_module(repo_root / 'upper_computer' / 'scripts' / 'final_audit.py')


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_yaml_compat_fallback_loads_repository_yaml_subset() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_module(repo_root / 'upper_computer' / 'scripts' / 'yaml_compat.py')

    payload = module._FallbackYamlParser('''
schema_version: 1
items:
- alpha
- beta
- color:red
- color:blue
- http://example.test
- topic:/arm/foo:bar
inline_objects:
- name: servo
  enabled: true
flow_map: {enabled: true, min_position: -3.14, label: servo}
wrapped_message: preview reserved profile keeps /stream in control-plane-only
  mode until an authoritative lane declares live ingress
''').parse()

    assert payload['schema_version'] == 1
    assert payload['items'] == [
        'alpha',
        'beta',
        'color:red',
        'color:blue',
        'http://example.test',
        'topic:/arm/foo:bar',
    ]
    assert payload['inline_objects'] == [{'name': 'servo', 'enabled': True}]
    assert payload['flow_map'] == {'enabled': True, 'min_position': -3.14, 'label': 'servo'}
    assert payload['wrapped_message'] == 'preview reserved profile keeps /stream in control-plane-only mode until an authoritative lane declares live ingress'


def test_upper_release_manifest_clean_first_run_records_hashes_and_self_reference(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_module(repo_root / 'upper_computer' / 'scripts' / 'package_release.py')
    (tmp_path / 'README.md').write_text('upper\n', encoding='utf-8')
    manifest = tmp_path / 'artifacts' / 'release_manifest.json'

    files = list(module.iter_release_files(tmp_path))
    assert manifest not in files
    module.write_release_manifest(files, output=manifest, root=tmp_path)
    payload = json.loads(manifest.read_text(encoding='utf-8'))
    expected_files = [path.relative_to(tmp_path).as_posix() for path in module._selected_release_files_with_manifest(tmp_path, manifest_path=manifest, files=files)]

    assert payload['schemaVersion'] == 2
    assert payload['generatedBy'] == 'scripts/package_release.py'
    assert payload['fileCount'] == len(expected_files)
    assert payload['files'] == expected_files
    records = {item['path']: item for item in payload['fileProvenance']}
    assert records['README.md']['provenanceStatus'] == 'recorded'
    assert records['README.md']['sizeBytes'] == (tmp_path / 'README.md').stat().st_size
    assert records['README.md']['sha256'] == _sha256(tmp_path / 'README.md')
    assert records['artifacts/release_manifest.json'] == {
        'path': 'artifacts/release_manifest.json',
        'sizeBytes': None,
        'sha256': None,
        'provenanceStatus': 'self_referential_manifest',
    }
    assert module.check_manifest(manifest_path=manifest, root=tmp_path) == []


def test_split_release_manifest_clean_first_run_records_hashes_and_self_reference(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_module(repo_root / 'scripts' / 'package_split_release.py')
    for rel, content in {
        '.gitignore': '*.pyc\n',
        'scripts/package_split_release.py': 'print("package")\n',
        'upper_computer/README.md': 'upper\n',
        'esp32s3_platformio/README.md': 'esp32\n',
        'stm32f103c8_platformio/README.md': 'stm32\n',
    }.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    manifest = tmp_path / 'artifacts' / 'split_release_manifest.json'
    for required in module.INCLUDED_ARTIFACTS:
        if required == Path('artifacts/split_release_manifest.json'):
            continue
        path = tmp_path / required
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'{required.as_posix()}\n', encoding='utf-8')

    files = list(module.iter_release_files(tmp_path))
    assert manifest not in files
    module.write_release_manifest(files, output=manifest, root=tmp_path)
    payload = json.loads(manifest.read_text(encoding='utf-8'))
    expected_files = [path.relative_to(tmp_path).as_posix() for path in module._selected_release_files_with_manifest(tmp_path, manifest_path=manifest, files=files)]

    assert payload['schemaVersion'] == 2
    assert payload['generatedBy'] == 'scripts/package_split_release.py'
    assert payload['fileCount'] == len(expected_files)
    assert payload['files'] == expected_files
    records = {item['path']: item for item in payload['fileProvenance']}
    assert records['upper_computer/README.md']['provenanceStatus'] == 'recorded'
    assert records['upper_computer/README.md']['sha256'] == _sha256(tmp_path / 'upper_computer' / 'README.md')
    assert records['artifacts/split_release_manifest.json'] == {
        'path': 'artifacts/split_release_manifest.json',
        'sizeBytes': None,
        'sha256': None,
        'provenanceStatus': 'self_referential_manifest',
    }
    assert module.check_manifest(manifest_path=manifest, root=tmp_path) == []


def test_release_manifest_check_fails_closed_when_manifest_missing(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_module(repo_root / 'upper_computer' / 'scripts' / 'package_release.py')
    (tmp_path / 'README.md').write_text('upper\n', encoding='utf-8')
    manifest = tmp_path / 'artifacts' / 'release_manifest.json'

    issues = module.check_manifest(manifest_path=manifest, root=tmp_path)

    assert issues == ['release manifest missing: artifacts/release_manifest.json']


def test_split_release_manifest_check_fails_closed_when_manifest_missing(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_module(repo_root / 'scripts' / 'package_split_release.py')
    for rel in ['.gitignore', 'scripts/package_split_release.py', 'upper_computer/README.md', 'esp32s3_platformio/README.md', 'stm32f103c8_platformio/README.md']:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel + '\n', encoding='utf-8')
    manifest = tmp_path / 'artifacts' / 'split_release_manifest.json'

    issues = module.check_manifest(manifest_path=manifest, root=tmp_path)

    assert issues == ['split release manifest missing: artifacts/split_release_manifest.json']


def test_release_manifest_check_flags_schema_metadata_drift(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_module(repo_root / 'upper_computer' / 'scripts' / 'package_release.py')
    (tmp_path / 'README.md').write_text('upper\n', encoding='utf-8')
    manifest = tmp_path / 'artifacts' / 'release_manifest.json'
    module.write_release_manifest(list(module.iter_release_files(tmp_path)), output=manifest, root=tmp_path)
    payload = json.loads(manifest.read_text(encoding='utf-8'))
    payload['schemaVersion'] = 1
    payload['generatedBy'] = 'manual'
    payload['fileCount'] = -1
    manifest.write_text(json.dumps(payload) + '\n', encoding='utf-8')

    issues = module.check_manifest(manifest_path=manifest, root=tmp_path)

    assert 'release manifest schemaVersion must be 2' in issues
    assert 'release manifest generatedBy drift detected' in issues
    assert 'release manifest fileCount drift detected' in issues


def test_release_manifest_check_flags_legacy_manifest_without_provenance(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_module(repo_root / 'upper_computer' / 'scripts' / 'package_release.py')
    (tmp_path / 'README.md').write_text('upper\n', encoding='utf-8')
    manifest = tmp_path / 'artifacts' / 'release_manifest.json'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    expected = [path.relative_to(tmp_path).as_posix() for path in module._selected_release_files_with_manifest(tmp_path, manifest_path=manifest)]
    manifest.write_text(json.dumps({'schemaVersion': 2, 'generatedBy': 'scripts/package_release.py', 'fileCount': len(expected), 'files': expected}) + '\n', encoding='utf-8')

    issues = module.check_manifest(manifest_path=manifest, root=tmp_path)

    assert 'release manifest missing fileProvenance records' in issues


def test_release_evidence_path_record_hashes_files_and_marks_self_reference() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_module(repo_root / 'upper_computer' / 'scripts' / 'collect_release_evidence.py')
    readme = module.ROOT / 'README.md'
    record = module._path_record(readme, output_path=module.ROOT / 'artifacts' / 'release_gates' / 'release_evidence.json')

    assert record['path'] == 'README.md'
    assert record['exists'] is True
    assert record['size'] == readme.stat().st_size
    assert record['sizeBytes'] == readme.stat().st_size
    assert record['sha256'] == _sha256(readme)
    assert record['provenanceStatus'] == 'recorded'

    clean_first_run_self = module.ROOT / 'artifacts' / 'release_gates' / 'release_evidence.clean-first-run-test.json'
    if clean_first_run_self.exists():
        clean_first_run_self.unlink()
    self_record = module._path_record(clean_first_run_self, output_path=clean_first_run_self)
    assert self_record['path'] == 'artifacts/release_gates/release_evidence.clean-first-run-test.json'
    assert self_record['exists'] is True
    assert self_record['selfReference'] is True
    assert self_record['size'] is None
    assert self_record['sizeBytes'] is None
    assert self_record['sha256'] is None
    assert self_record['provenanceStatus'] == 'self_referential_output'


def test_final_audit_rejects_self_reference_stale_size() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_final_audit_module(repo_root)

    issues = module._audit_release_evidence_file_provenance({
        'evidence': [
            {
                'path': 'artifacts/release_gates/release_evidence.json',
                'exists': True,
                'size': 1,
                'sizeBytes': None,
                'sha256': None,
                'provenanceStatus': 'self_referential_output',
            }
        ]
    })

    assert issues == ['release_evidence.json self-reference must not record stale hash/size: artifacts/release_gates/release_evidence.json']


def test_collect_default_output_marks_canonical_release_evidence_self_reference() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_module(repo_root / 'upper_computer' / 'scripts' / 'collect_release_evidence.py')

    payload = module.collect()
    records = [
        item for item in payload['evidence']
        if isinstance(item, dict) and item.get('path') == 'artifacts/release_gates/release_evidence.json'
    ]

    assert len(records) == 1
    record = records[0]
    assert record['exists'] is True
    assert record['selfReference'] is True
    assert record['size'] is None
    assert record['sizeBytes'] is None
    assert record['sha256'] is None
    assert record['provenanceStatus'] == 'self_referential_output'


def test_collect_rejects_release_evidence_output_outside_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_module(repo_root / 'upper_computer' / 'scripts' / 'collect_release_evidence.py')

    try:
        module.collect(Path('/tmp/release_evidence.outside-root.json'))
    except ValueError as exc:
        assert 'release evidence path must be inside upper_computer root' in str(exc)
    else:
        raise AssertionError('collect() must reject release evidence output outside ROOT')


def test_final_audit_rejects_missing_release_evidence_self_reference() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_final_audit_module(repo_root)

    issues = module._audit_release_evidence_file_provenance({'evidence': []})

    assert issues == ['release_evidence.json missing self-reference entry: artifacts/release_gates/release_evidence.json']


def test_final_audit_rejects_duplicate_release_evidence_self_reference() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_final_audit_module(repo_root)
    self_record = {
        'path': 'artifacts/release_gates/release_evidence.json',
        'exists': True,
        'size': None,
        'sizeBytes': None,
        'sha256': None,
        'provenanceStatus': 'self_referential_output',
    }

    issues = module._audit_release_evidence_file_provenance({'evidence': [dict(self_record), dict(self_record)]})

    assert issues == ['release_evidence.json duplicate self-reference entry: artifacts/release_gates/release_evidence.json']


def test_split_release_manifest_check_flags_schema_metadata_drift(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    module = _load_module(repo_root / 'scripts' / 'package_split_release.py')
    for rel, content in {
        '.gitignore': '*.pyc\n',
        'scripts/package_split_release.py': 'print("package")\n',
        'upper_computer/README.md': 'upper\n',
        'esp32s3_platformio/README.md': 'esp32\n',
        'stm32f103c8_platformio/README.md': 'stm32\n',
    }.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    manifest = tmp_path / 'artifacts' / 'split_release_manifest.json'
    for required in module.INCLUDED_ARTIFACTS:
        if required == Path('artifacts/split_release_manifest.json'):
            continue
        path = tmp_path / required
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'{required.as_posix()}\n', encoding='utf-8')
    module.write_release_manifest(list(module.iter_release_files(tmp_path)), output=manifest, root=tmp_path)
    payload = json.loads(manifest.read_text(encoding='utf-8'))
    payload['schemaVersion'] = 1
    payload['generatedBy'] = 'manual'
    payload['fileCount'] = -1
    manifest.write_text(json.dumps(payload) + '\n', encoding='utf-8')

    issues = module.check_manifest(manifest_path=manifest, root=tmp_path)

    assert 'split release manifest schemaVersion must be 2' in issues
    assert 'split release manifest generatedBy drift detected' in issues
    assert 'split release manifest fileCount drift detected' in issues


def test_ros_target_validation_finalizer_collects_evidence_after_gate_report() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / 'upper_computer' / 'scripts' / 'ros_target_validation.sh').read_text(encoding='utf-8')
    finalize_start = script.index('finalize() {')
    finalize_end = script.index("trap 'finalize", finalize_start)
    finalize_body = script[finalize_start:finalize_end]

    assert '|| true' not in finalize_body
    assert finalize_body.index('write_gate_report') < finalize_body.index('collect_release_evidence.py')
