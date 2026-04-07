import type { CommandSummary } from '@/models/readiness';
import type { HardwareState } from '@/models/robot';

export function deriveCommandPillClass(commandSummary: CommandSummary | undefined, totalCommandCount: number): string {
  if (!totalCommandCount) return 'status-warn';
  if ((commandSummary?.blockedCount || 0) === 0) return 'status-ok';
  if ((commandSummary?.readyCount || 0) > 0) return 'status-warn';
  return 'status-danger';
}

export function deriveHardwareTransportLabel(hardware: HardwareState | null | undefined): string {
  if (!hardware?.sourceStm32Online && hardware?.sourceStm32TransportMode !== 'simulated') return 'STM32 OFF';
  if (hardware?.sourceStm32SimulatedFallback) return 'STM32 FALLBACK';
  if (hardware?.sourceStm32Simulated) return 'STM32 SIM';
  if (hardware?.sourceStm32Online && hardware?.sourceStm32Controllable === false) return 'STM32 LIMITED';
  if (hardware?.sourceStm32Online && hardware?.sourceStm32Authoritative === false) return 'STM32 UNAUTH';
  return 'STM32';
}

export function deriveHardwareTransportClass(hardware: HardwareState | null | undefined): string {
  if (!hardware?.sourceStm32Online && hardware?.sourceStm32TransportMode !== 'simulated') return 'status-danger';
  if (hardware?.sourceStm32SimulatedFallback || hardware?.sourceStm32Simulated) return 'status-warn';
  if (hardware?.sourceStm32Controllable === false || hardware?.sourceStm32Authoritative === false) return 'status-warn';
  return 'status-ok';
}
