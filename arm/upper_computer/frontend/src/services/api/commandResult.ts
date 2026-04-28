import type { CommandTransportResult as GeneratedCommandTransportResult, StartTaskDecision } from '@/api/generated';

export type CommandTransportResult = GeneratedCommandTransportResult;
export type CommandDecisionLike = GeneratedCommandTransportResult | StartTaskDecision | undefined;
export type CommandLifecycleStatus = NonNullable<GeneratedCommandTransportResult['authoritativeStatus']>;

export function commandAccepted(result: CommandDecisionLike): boolean {
  if (!result) return false;
  if (typeof result.accepted === 'boolean') return result.accepted;
  if ('success' in result && typeof result.success === 'boolean') return result.success;
  return false;
}

export function commandCompletionPending(result: CommandDecisionLike): boolean {
  if (!result) return false;
  return Boolean(result.completionPending ?? false);
}

export function describeAcceptedCommand(result: CommandDecisionLike, acceptedMessage: string, previewMessage: string): string {
  return result?.localPreviewOnly ? previewMessage : acceptedMessage;
}
