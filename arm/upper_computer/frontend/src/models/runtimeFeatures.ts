import type { ReadinessState } from '@/models/readiness';
import { PRODUCT_LINE_CAPABILITIES } from '@/generated/runtimeContract';

export interface RuntimeFeatureState {
  authoritativeRuntime: boolean;
  previewRuntime: boolean;
  runtimeTier: 'preview' | 'validated_sim' | 'validated_live';
  runtimeLabel: string;
  runtimeBadge: string;
  promotionControlled: boolean;
  promotionEffective: boolean;
  promotionMissing: string[];
  taskWorkbenchVisible: boolean;
  taskExecutionInteractive: boolean;
  taskStartReason: string;
}

const DEFAULT_PREVIEW_REASON = '当前 runtime 不是 authoritative lane，任务工作台保持只读。';

type RuntimeTier = RuntimeFeatureState['runtimeTier'];
type ProductLineCapability = typeof PRODUCT_LINE_CAPABILITIES[keyof typeof PRODUCT_LINE_CAPABILITIES];

function resolveProductLineCapability(runtimeTier: RuntimeTier): ProductLineCapability {
  return PRODUCT_LINE_CAPABILITIES[runtimeTier] ?? PRODUCT_LINE_CAPABILITIES.preview;
}

/**
 * Derive operator-facing runtime features from the latest readiness snapshot.
 *
 * Args:
 *   readiness: Gateway readiness snapshot. Missing or partial snapshots degrade
 *     to preview-tier behavior.
 *
 * Returns:
 *   RuntimeFeatureState: Product-line visibility, interactivity, promotion, and
 *   user-facing reason strings synchronized with the generated runtime contract.
 *
 * Boundary behavior:
 *   - Unknown runtime tiers degrade to preview.
 *   - The public UI surface prefers `runtimeSurfaceState` and only falls back to
 *     compatibility aliases when the compatibility layer is all that is available.
 */
export function deriveRuntimeFeatureState(readiness: Partial<ReadinessState> | null | undefined): RuntimeFeatureState {
  const projected = readiness?.runtimeSurfaceState;
  if (projected && typeof projected === 'object') {
    const taskExecutionState = readiness?.taskExecutionState || projected.taskExecutionState;
    const runtimeTier = ((taskExecutionState?.runtimeTier || projected.runtimeTier) && ['preview', 'validated_sim', 'validated_live'].includes(taskExecutionState?.runtimeTier || projected.runtimeTier)
      ? (taskExecutionState?.runtimeTier || projected.runtimeTier)
      : 'preview') as RuntimeTier;
    const productLine = resolveProductLineCapability(runtimeTier);
    const startPolicy = readiness?.commandPolicies?.startTask;
    const startAllowed = Boolean(taskExecutionState?.startAllowed ?? startPolicy?.allowed ?? projected.taskExecutionInteractive);
    const missing = Array.isArray(taskExecutionState?.promotionMissing) && taskExecutionState?.promotionMissing.length
      ? [...taskExecutionState.promotionMissing]
      : Array.isArray(productLine.promotionMissing)
        ? [...productLine.promotionMissing]
        : [];
    const startMissing = Array.isArray(taskExecutionState?.startMissingDetails) && taskExecutionState.startMissingDetails.length
      ? taskExecutionState.startMissingDetails.map((item) => `${item.name}(${item.detail})`)
      : Array.isArray(taskExecutionState?.startMissingChecks)
        ? [...taskExecutionState.startMissingChecks]
        : [];
    const deniedReason = typeof taskExecutionState?.reason === 'string' && taskExecutionState.reason
      ? taskExecutionState.reason
      : typeof startPolicy?.reason === 'string' && startPolicy.reason
        ? startPolicy.reason
        : '';
    const taskWorkbenchVisible = Boolean(taskExecutionState?.workbenchVisible ?? projected.taskWorkbenchVisible);
    const taskExecutionInteractive = taskWorkbenchVisible && Boolean(taskExecutionState?.interactive ?? projected.taskExecutionInteractive) && startAllowed;
    const authoritativeRuntime = Boolean(readiness?.authorityState?.authoritativeRuntime ?? projected.authorityState?.authoritativeRuntime ?? taskWorkbenchVisible);

    let taskStartReason: string = productLine.description;
    if (!taskWorkbenchVisible) {
      taskStartReason = deniedReason || (missing.length
        ? `当前 runtime 缺少 authoritative 前提：${missing.join(' / ')}`
        : DEFAULT_PREVIEW_REASON);
    } else if (!taskExecutionInteractive) {
      taskStartReason = deniedReason || (startMissing.length
        ? `任务工作台已开放，但当前禁止发令：${startMissing.join(' / ')}`
        : missing.length
          ? `任务工作台已开放，但当前禁止发令：${missing.join(' / ')}`
          : '任务工作台已开放，但当前 startTask 策略未放行。');
    } else if (runtimeTier === 'validated_live') {
      taskStartReason = 'validated live hardware lane 已启用，可进入真机任务工作台。';
    } else if (runtimeTier === 'validated_sim') {
      taskStartReason = 'validated simulation lane 已启用，可进入正式任务工作台。';
    }

    return {
      authoritativeRuntime,
      previewRuntime: !taskWorkbenchVisible,
      runtimeTier,
      runtimeLabel: projected.runtimeLabel || productLine.label,
      runtimeBadge: projected.runtimeBadge || productLine.runtimeBadge,
      promotionControlled: Boolean(taskExecutionState?.promotionControlled ?? productLine.promotionControlled),
      promotionEffective: Boolean(taskExecutionState?.promotionEffective ?? productLine.promotionEffective),
      promotionMissing: missing,
      taskWorkbenchVisible,
      taskExecutionInteractive,
      taskStartReason,
    };
  }

  const runtimeTier = (readiness?.runtimeTier && ['preview', 'validated_sim', 'validated_live'].includes(readiness.runtimeTier)
    ? readiness.runtimeTier
    : 'preview') as RuntimeTier;
  const productLine = resolveProductLineCapability(runtimeTier);
  const startPolicy = readiness?.commandPolicies?.startTask;
  const startAllowed = Boolean(startPolicy?.allowed);
  const missing = Array.isArray(readiness?.runtimeMissingChecks) ? readiness.runtimeMissingChecks.filter(Boolean) : [];
  const source = typeof readiness?.source === 'string' ? readiness.source : '';
  const deniedReason = typeof startPolicy?.reason === 'string' && startPolicy.reason ? startPolicy.reason : '';
  const startMissing = Array.isArray(readiness?.taskExecutionState?.startMissingDetails) && readiness?.taskExecutionState?.startMissingDetails?.length
    ? readiness.taskExecutionState.startMissingDetails.map((item) => `${item.name}(${item.detail})`)
    : [];
  const taskWorkbenchVisible = Boolean(productLine.taskWorkbenchVisible);
  const taskExecutionInteractive = taskWorkbenchVisible && Boolean(productLine.taskExecutionInteractive) && startAllowed;
  const authoritativeRuntime = taskWorkbenchVisible;
  const previewRuntime = !authoritativeRuntime;

  let taskStartReason: string = productLine.description;
  if (!taskWorkbenchVisible) {
    taskStartReason = deniedReason || (missing.length
      ? `当前 runtime 缺少 authoritative 前提：${missing.join(' / ')}`
      : source
        ? `${DEFAULT_PREVIEW_REASON} 来源：${source}`
        : DEFAULT_PREVIEW_REASON);
  } else if (!taskExecutionInteractive) {
    taskStartReason = deniedReason || (startMissing.length
      ? `任务工作台已开放，但当前禁止发令：${startMissing.join(' / ')}`
      : missing.length
        ? `任务工作台已开放，但当前禁止发令：${missing.join(' / ')}`
        : '任务工作台已开放，但当前 startTask 策略未放行。');
  } else if (runtimeTier === 'validated_live') {
    taskStartReason = 'validated live hardware lane 已启用，可进入真机任务工作台。';
  } else if (runtimeTier === 'validated_sim') {
    taskStartReason = 'validated simulation lane 已启用，可进入正式任务工作台。';
  }

  return {
    authoritativeRuntime,
    previewRuntime,
    runtimeTier,
    runtimeLabel: productLine.label,
    runtimeBadge: productLine.runtimeBadge,
    promotionControlled: Boolean(productLine.promotionControlled),
    promotionEffective: Boolean(productLine.promotionEffective),
    promotionMissing: Array.isArray(productLine.promotionMissing) ? [...productLine.promotionMissing] : [],
    taskWorkbenchVisible,
    taskExecutionInteractive,
    taskStartReason,
  };
}
