# Verification and Release

> Audience: maintainers, reviewers, release operators
> Owner: release / QA
> Status: canonical
> Source of Truth: Makefiles, verification scripts, final audit, release gate artifacts
> Last Update Rule: verification commands, release gates, or evidence boundaries change together.

> 统一术语引用：本文涉及的 repository validation lane、target runtime lane、HIL / release lane，以及“已静态确认 / 已沙箱验证 / 未真实环境验证”的结果表述规则，统一见 [`../architecture/terms-and-reference-blocks.md` §4](../architecture/terms-and-reference-blocks.md#4-验证与发布术语块)。

## 1. 本文负责什么 / 不负责什么

### 本文负责

- 仓库级验证分层
- release gate 的组成
- 证据归档边界
- 结果表述约束

### 本文不负责

- 不定义 runtime lane / promotion 语义
- 不记录某次 smoke report 的结果细节
- 不替代 evidence 文档

## 2. 验证目标

本文件定义：

- 仓库级验证分层
- release gate 的组成
- 哪些材料必须进入 evidence，而不是留在 README 里

## 3. 验证分层

### Repository validation lane

- Linux
- Python 3.10+
- Node 22.x
- npm 10.9.2
- 可在无 ROS2 环境执行仓库级单元/契约/前端/打包门禁

### Target runtime lane

- Ubuntu 22.04 LTS
- ROS 2 Humble
- active overlay / launch / target runtime gate / HIL 相关依赖

### HIL / release lane

- 面向 validated_live promotion
- 需要 target runtime gate、HIL smoke、release checklist、evidence 归档

完整定义见 [`terms-and-reference-blocks.md` §4](../architecture/terms-and-reference-blocks.md#4-验证与发布术语块)。

## 4. 推荐验证顺序

1. contract / generation 验证
2. gateway / backend / frontend 测试
3. final audit
4. package / release evidence
5. target runtime / HIL（如涉及 validated_live）

## 5. 常用命令

### 仓库级

```bash
python scripts/generate_contract_artifacts.py --check
python scripts/validate_runtime_contracts.py
pytest -q gateway/tests
python scripts/verify_frontend_validation.py
python scripts/write_frontend_validation_status.py
python scripts/sync_doc_compatibility_mirrors.py --check
python scripts/final_audit.py
```

### 前端

```bash
cd frontend
npm ci
npm run typecheck
npm run typecheck:test
npm run test:unit
npm run build
```

### release / package

```bash
python scripts/collect_release_evidence.py
python scripts/package_release.py
```

Release manifest 与 release evidence 必须同时保留兼容字段和文件级 provenance：

- `artifacts/release_manifest.json` 与顶层 `artifacts/split_release_manifest.json` 继续保留 `files`，同时写入一一对应的 `fileProvenance`。
- clean first-run 下 manifest 即使尚未存在，也必须被纳入本次 package selection；写 manifest 与打 release archive 必须使用同一份 selection。
- 常规文件 provenance 必须包含 `path`、`sizeBytes`、`sha256`、`provenanceStatus=recorded`。
- manifest 自身不能写入自己的最终 SHA-256；对应记录必须使用 `provenanceStatus=self_referential_manifest`，且 `sha256/sizeBytes` 为 `null`。
- `python scripts/package_release.py --check` 与 `python ../scripts/package_split_release.py --check` 必须 fail closed：manifest 缺失、`schemaVersion/generatedBy/fileCount` 漂移、`files` 漂移或 `fileProvenance` 漂移均视为 release gate 问题。
- `artifacts/release_gates/release_evidence.json` 对普通证据文件记录 `size/sizeBytes/sha256`；对自身输出必须且只能存在一个 `provenanceStatus=self_referential_output` 记录，记录 post-write `exists=true`，并禁止写入生成前的 stale `size/sizeBytes/sha256`。
- `collect_release_evidence.py` 在未传 `--out` 时默认以 canonical `artifacts/release_gates/release_evidence.json` 作为自身 self-reference；`--out` 只能指向 `upper_computer/` 仓库内路径，仓库外路径必须失败，避免 release ledger 出现不可审计的绝对路径。正式 final audit 仍以 canonical `artifacts/release_gates/release_evidence.json` 为 release ledger。
- target validation finalizer 必须先写 `target_runtime_gate.json`，再收集 `release_evidence.json`；release evidence 收集失败不得被 `|| true` 静默吞掉。
- release/provenance 定向回归入口为 `python scripts/run_provenance_regression.py`，该入口只依赖 Python 标准库，必须执行 `tests/test_release_manifest_provenance.py` 中全部 `test_*` 函数；新增必需 fixture 时必须 fail closed，不能被静默跳过。
- `final_audit.py`、`runtime_authority.py` 及其直接 release 依赖脚本在缺少 PyYAML 的最小 Python 环境中必须通过 `scripts/yaml_compat.py` 读取仓库内 YAML 子集；正式环境安装 PyYAML 时仍优先使用 PyYAML。fallback 必须保持仓库内合法 plain scalar 语义：`color:red`、URL、topic/path 中的无空格冒号仍是字符串，只有 `key: value` 或 `key:` 形式可作为 inline mapping。

## 6. Release gates

release gate 至少关注：

- generated contracts 同步
- gateway/front/backend 的公共合同一致
- firmware build / split repository gate
- 文档 compatibility mirror 与 canonical/source gate 同步
- final audit 通过
- evidence ledger 与归档齐全

对于 validated_live，还必须满足：

- `validated_live_backbone_declared`
- `target_runtime_gate_passed`
- `hil_gate_passed`
- `release_checklist_signed`

## 7. Traceability

P0/P1/P2 的实现验证不应只留在口头结论里；至少要在：

- gateway tests
- frontend tests
- contract checks
- evidence 文档 / JSON ledger
- final audit

中留下对应证据，不再依赖旧的顶层 traceability 文档。

当前 traceability 基线最少覆盖：

- arm interfaces / mirror contract tests
- runtime lane truthfulness tests
- planner / executor / provider boundary tests
- launch / lane layout tests
- camera → perception → HMI frame summary tests
- reset fault / recover / maintenance closure tests

### Release-specific closure note

- servo-cartesian endpoint is wired through gateway validation, dispatcher mapping, and transport feedback closure

## 8. 证据归档矩阵

| 验证面 | 结果应该落在哪里 |
|---|---|
| 前端构建 / typecheck / unit / e2e 结果 | `evidence/frontend-validation-status.md` + `../../artifacts/release_gates/frontend_validation_ledger.json` |
| validated_live smoke / checklist / gate | `evidence/validated_live/` |
| 兼容性回归结论 | `evidence/compatibility-regression.md` |
| generated contract / acceptance matrix | `generated/` |

## 9. 结果表述规则

本文件不再重复列出允许/禁止写法，统一见 [`terms-and-reference-blocks.md` §4.4](../architecture/terms-and-reference-blocks.md#44-结果表述)。

## 10. 与 evidence 的关系

规则、流程、门禁写在本文件；

具体 smoke report、validation status、promotion 签收材料，统一放到 `../evidence/`。
