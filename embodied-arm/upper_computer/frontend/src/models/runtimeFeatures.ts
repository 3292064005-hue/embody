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
 *   - Task workbench visibility follows the promoted product line.
 *   - Task execution interactivity additionally requires ``startTask.allowed``.
 */
export function deriveRuntimeFeatureState(readiness: Partial<ReadinessState> | null | undefined): RuntimeFeatureState {
  const runtimeTier = (readiness?.runtimeTier && ['preview', 'validated_sim', 'validated_live'].includes(readiness.runtimeTier)
    ? readiness.runtimeTier
    : 'preview') as RuntimeTier;
  const productLine = resolveProductLineCapability(runtimeTier);
  const startPolicy = readiness?.commandPolicies?.startTask;
  const startAllowed = Boolean(startPolicy?.allowed);
  const missing = Array.isArray(readiness?.runtimeMissingChecks) ? readiness?.runtimeMissingChecks.filter(Boolean) : [];
  const source = typeof readiness?.source === 'string' ? readiness.source : '';
  const deniedReason = typeof startPolicy?.reason === 'string' && startPolicy.reason ? startPolicy.reason : '';
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
    taskStartReason = deniedReason || (missing.length
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
