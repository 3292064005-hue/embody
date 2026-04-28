# Frontend Validation Status

> Status: evidence
> Canonical verification rules: `../operations/verification-and-release.md`
> Machine-readable ledger: `../../artifacts/release_gates/frontend_validation_ledger.json`

本文件只记录最近一次可审计的前端验证矩阵与产物位置；规则、门槛与命令仍以 canonical verification 文档为准。若走手工前端验证路径，必须先执行 `python scripts/verify_frontend_validation.py` 生成 auditable summary，再运行本脚本。

- overall status: `blocked`
- source profile: `release_gates`
- source summary: `artifacts/repository_validation/release_gates/verification_summary.json`
- generated at: `2026-04-20T16:01:37Z`

## Environment contract snapshot
- Node.js: `>=22 <23`
- package manager: `npm@10.9.2`

## Validation matrix

| Step | Group | Status | Required | Blocking Class | Log |
|---|---|---|---|---|---|
| dependency install (npm ci) | dependencies | `blocked` | yes | `none` | `artifacts/repository_validation/release_gates/frontend-deps.log` |
| application typecheck | typecheck | `not_executed` | yes | `none` | `artifacts/repository_validation/release_gates/frontend-typecheck-app.log` |
| test-only typecheck | typecheck | `not_executed` | yes | `none` | `artifacts/repository_validation/release_gates/frontend-typecheck-test.log` |
| unit tests | tests | `not_executed` | yes | `none` | `artifacts/repository_validation/release_gates/frontend-unit.log` |
| frontend build (profile unknown) | build | `not_executed` | yes | `none` | `artifacts/repository_validation/release_gates/frontend-build.log` |
| playwright e2e | tests | `not_executed` | yes | `none` | `artifacts/repository_validation/release_gates/frontend-e2e.log` |

## Interpretation
- `passed`: 该步骤已在当前 evidence 来源中成功完成。
- `failed`: 该步骤在 evidence 来源中失败；需要查看对应 log。
- `skipped`: 该步骤由于环境前置条件缺失而被显式跳过，不能视为通过。
- `blocked`: 整体状态使用；表示存在跳过/阻塞步骤，验证链必须 fail-closed。
- `not_executed`: 当前仓库内没有可审计的最近一次执行记录。
- `partial`: 仅整体状态会使用；表示矩阵中存在已执行与未执行混合情况。

## Maintenance rule
- 该 evidence 文件与 JSON ledger 由脚本生成，不应手工编辑。
- 当 repository validation lane 的前端步骤、日志布局或命名变化时，需同步更新生成脚本。

