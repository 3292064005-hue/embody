from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAINTENANCE_PAGE = ROOT / 'frontend' / 'src' / 'pages' / 'MaintenancePage.vue'
FRONTEND_RUNTIME_CONTRACT = ROOT / 'frontend' / 'src' / 'generated' / 'runtimeContract.ts'
READINESS_STORE = ROOT / 'frontend' / 'src' / 'stores' / 'readiness.ts'


def test_maintenance_page_exposes_all_six_joints() -> None:
    text = MAINTENANCE_PAGE.read_text(encoding='utf-8')
    assert 'Array.from({ length: 6 })' in text


def test_maintenance_page_prefers_runtime_readiness_limits_with_generated_fallback() -> None:
    page_text = MAINTENANCE_PAGE.read_text(encoding='utf-8')
    contract_text = FRONTEND_RUNTIME_CONTRACT.read_text(encoding='utf-8')
    readiness_store_text = READINESS_STORE.read_text(encoding='utf-8')
    assert "import { useReadinessStore } from '@/stores/readiness';" in page_text
    assert "import { MANUAL_COMMAND_LIMITS } from '@/generated/runtimeContract';" in page_text
    assert 'const effectiveManualCommandLimits = computed(() => readinessStore.manualCommandLimits || MANUAL_COMMAND_LIMITS);' in page_text
    assert ':max="effectiveManualCommandLimits.maxJogJointStepDeg"' in page_text
    assert 'export const MANUAL_COMMAND_LIMITS =' in contract_text
    assert 'manualCommandLimits:' in readiness_store_text


def test_maintenance_page_servo_limit_tracks_runtime_readiness_limits() -> None:
    page_text = MAINTENANCE_PAGE.read_text(encoding='utf-8')
    contract_text = FRONTEND_RUNTIME_CONTRACT.read_text(encoding='utf-8')
    assert 'const maxServoStepMm = computed(() => Math.round(effectiveManualCommandLimits.value.maxServoCartesianDeltaMeters * 1000));' in page_text
    assert 'if (servoStep.value > maxServoStepMm.value) servoStep.value = maxServoStepMm.value;' in page_text
    assert ':max="maxServoStepMm"' in page_text
    assert '"maxServoCartesianDeltaMeters": 0.1' in contract_text
