import { describe, expect, it } from 'vitest';

import { deriveCommandPillClass, deriveHardwareTransportClass, deriveHardwareTransportLabel } from '@/components/system/statusSemantics';
import type { HardwareState } from '@/models/robot';

function hw(overrides: Partial<HardwareState>): HardwareState {
  return {
    joints: [],
    gripperOpen: false,
    homed: false,
    limits: [],
    busy: false,
    ...overrides,
  };
}

describe('status semantics', () => {
  it('derives command pill classes from command summary branches', () => {
    expect(deriveCommandPillClass(undefined, 0)).toBe('status-warn');
    expect(deriveCommandPillClass({ allowed: ['a'], blocked: [], readyCount: 1, blockedCount: 0 }, 1)).toBe('status-ok');
    expect(deriveCommandPillClass({ allowed: ['a'], blocked: ['b'], readyCount: 1, blockedCount: 1 }, 2)).toBe('status-warn');
    expect(deriveCommandPillClass({ allowed: [], blocked: ['a'], readyCount: 0, blockedCount: 1 }, 1)).toBe('status-danger');
  });

  it('derives hardware transport labels for all exposed branches', () => {
    expect(deriveHardwareTransportLabel(hw({ sourceStm32Online: false, sourceStm32TransportMode: 'unavailable' }))).toBe('STM32 OFF');
    expect(deriveHardwareTransportLabel(hw({ sourceStm32Online: true, sourceStm32ExecutionSemantics: 'preview_simulated_transport', sourceStm32ExecutionPreviewOnly: true }))).toBe('STM32 PREVIEW');
    expect(deriveHardwareTransportLabel(hw({ sourceStm32Online: true, sourceStm32ExecutionSemantics: 'authoritative_simulated_transport', sourceStm32Authoritative: true, sourceStm32Controllable: true }))).toBe('STM32 AUTH-SIM');
    expect(deriveHardwareTransportLabel(hw({ sourceStm32Online: true, sourceStm32SimulatedFallback: true }))).toBe('STM32 FALLBACK');
    expect(deriveHardwareTransportLabel(hw({ sourceStm32Online: true, sourceStm32Simulated: true }))).toBe('STM32 SIM');
    expect(deriveHardwareTransportLabel(hw({ sourceStm32Online: true, sourceStm32ExecutionSemantics: 'non_authoritative_real_link', sourceStm32Authoritative: false, sourceStm32Controllable: true }))).toBe('STM32 LINK ONLY');
    expect(deriveHardwareTransportLabel(hw({ sourceStm32Online: true, sourceStm32Controllable: false }))).toBe('STM32 LIMITED');
    expect(deriveHardwareTransportLabel(hw({ sourceStm32Online: true, sourceStm32Authoritative: false, sourceStm32Controllable: true }))).toBe('STM32 UNAUTH');
    expect(deriveHardwareTransportLabel(hw({ sourceStm32Online: true, sourceStm32Authoritative: true, sourceStm32Controllable: true }))).toBe('STM32');
  });

  it('derives hardware transport classes for all exposed branches', () => {
    expect(deriveHardwareTransportClass(hw({ sourceStm32Online: false, sourceStm32TransportMode: 'unavailable' }))).toBe('status-danger');
    expect(deriveHardwareTransportClass(hw({ sourceStm32Online: true, sourceStm32ExecutionPreviewOnly: true, sourceStm32ExecutionSemantics: 'preview_simulated_transport' }))).toBe('status-warn');
    expect(deriveHardwareTransportClass(hw({ sourceStm32Online: true, sourceStm32ExecutionSemantics: 'authoritative_simulated_transport', sourceStm32Authoritative: true, sourceStm32Controllable: true }))).toBe('status-ok');
    expect(deriveHardwareTransportClass(hw({ sourceStm32Online: true, sourceStm32SimulatedFallback: true }))).toBe('status-warn');
    expect(deriveHardwareTransportClass(hw({ sourceStm32Online: true, sourceStm32Simulated: true }))).toBe('status-warn');
    expect(deriveHardwareTransportClass(hw({ sourceStm32Online: true, sourceStm32Controllable: false }))).toBe('status-warn');
    expect(deriveHardwareTransportClass(hw({ sourceStm32Online: true, sourceStm32Authoritative: false, sourceStm32Controllable: true }))).toBe('status-warn');
    expect(deriveHardwareTransportClass(hw({ sourceStm32Online: true, sourceStm32Authoritative: true, sourceStm32Controllable: true }))).toBe('status-ok');
  });
});
