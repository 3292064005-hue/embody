from __future__ import annotations

from scripts.write_release_gate_report import build_gate_report


def test_target_runtime_gate_report_surfaces_negative_path_coverage_and_readiness() -> None:
    report = build_gate_report({}, {'env': 'passed', 'ros_build': 'passed', 'ros_smoke': 'passed', 'negative_path_subset': 'blocked', 'hil': 'blocked'})
    assert report['hasBlockingStep'] is True
    assert report['negativePathCoverage']['automaticSubset'] == 'blocked'
    assert report['targetRuntimeReadiness'] == 'blocked'
