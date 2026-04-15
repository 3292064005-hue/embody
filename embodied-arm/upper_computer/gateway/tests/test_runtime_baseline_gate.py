from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_runtime_baseline_gate import evaluate_report


def test_runtime_baseline_gate_blocks_on_action_bound_voice_or_missing_tier() -> None:
    evaluation = evaluate_report(
        {
            'counts': {'taskRunFinished': 1},
            'taskRunStatus': {'failed': 0},
            'voiceTelemetry': {'actionBoundEvents': 1},
            'runtimeTiers': {'preview': 1},
        },
        thresholds={
            'min_task_run_finished': 1,
            'max_failed_task_runs': 0,
            'max_action_bound_voice_events': 0,
            'require_runtime_tiers': ['validated_sim'],
        },
    )
    assert evaluation['status'] == 'blocked'
    assert 'voiceActionBoundEvents' in evaluation['missingChecks']
    assert 'requiredRuntimeTiers' in evaluation['missingChecks']
