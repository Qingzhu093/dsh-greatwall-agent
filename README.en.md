# Great Wall Agent V4.2 — DeepSeek Harness plugin (`dsh-greatwall-agent`)

> **In one sentence**: the long-horizon, unattended AI-for-Science / algorithm-competition campaign plugin originally written for Google Antigravity, ported to **DeepSeek Harness (DSH)** — with the **Python core shipped byte-for-byte unchanged** and only the host adapter rewritten: MCP bridge, skill registration, and the clean-room gate.

| Item | Value |
| :--- | :--- |
| npm package | `dsh-greatwall-agent` |
| Version | `4.2.0` |
| DSH requirement | `>=0.2.2-rc.1 <0.3.0-0` (`engines.dsh`) |
| Node requirement | `^22.19.0 \|\| >=24.0.0` (`engines.node`) |
| License | MIT ([`LICENSE`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/LICENSE)) |
| Source repository | <https://github.com/Qingzhu093/dsh-greatwall-agent> (after release) |
| Original Antigravity plugin | `plugins/greatwall-agent/` in the design repo (read-only); `greatwall-agent/` here is a byte-identical copy |

---

## 1. What this package is

The Antigravity plugin has two layers:

- a **portable core**: `lib/*.py` + `bin/gw_mcp_server.py` + `bin/hook_gate.py`, implemented with the Python standard library only;
- an **Antigravity host shell**: `plugin.json`, `mcp_config.json`, `hooks.json`, `skills/`, `rules/`, `agents/`.

DSH has a different host contract, so this package does exactly two things:

1. it ships the **entire original plugin tree byte-for-byte** under [`greatwall-agent/`](https://github.com/Qingzhu093/dsh-greatwall-agent/tree/main/greatwall-agent), and makes "we did not change a line" machine-checkable with `core-manifest.sha256` (18 files);
2. it re-implements the three host capabilities in [`lib/index.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/index.js), [`lib/gate.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/gate.js) and [`lib/skillpack.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/skillpack.js): mount the MCP server, register the skill, install the clean-room tool guard.

You are not getting a "behaviourally similar" rewrite: it is the **same core plus a new host adapter**. Tool arguments, return values and adjudication logic are identical to the original plugin.

---

## 2. Features

1. **Phase 0 opening distillation** (`gw_init_campaign` + `gw_lock_distillation`): deterministic EDA data probe, locked disambiguation, orthogonal method families / obsolete-model blacklist / build-vs-buy contract, and an in-sandbox tournament over M candidate baselines that mints the anchor baseline `s_0`.
2. **Git-free clean-room slots** (`gw_allocate_slot` + `gw_surgical_replace`): check out an island from the kernel snapshot, auto-assemble the L1 `scoped_brief.md`, and hot-swap a single target block `c_t` by AST instead of rewriting whole files.
3. **Cross-process anti-cheat evaluation** (`gw_evaluate_slot`): AST forensics (leakage, obsolete models, wheel reinvention, multimodal completeness, structural-diff ratio), four-tuple novelty stripping, isomorphic perturbation, and an HMAC-SHA256-signed `metrics_receipt.json` with four-way triage.
4. **Zero-vector L0/L1/L2 archive** (`gw_submit_legacy` + `gw_archive_query`): five-item legacy acceptance, primitive sandbox unit tests, signature-only `PRIMITIVES_API.md`, cross-lineage citation counting, and retraction of dependent claims.
5. **Lineage control and the 60-step reflection chamber** (`gw_lineage_control`): in-place soft flush, ancestor hard fork, 3-turn reflection contract, cross-branch differential testing, and retroactive errata re-scoring.
6. **Anti-bluff final delivery** (`gw_compile_delivery`): blocks `TODO / TBD / Conclusions Here`, binds every score table to HMAC receipts, and builds the `final_delivery/` envelope.
7. **Clean-room gate** (the DSH port of the original `PreToolUse` hook): the same three rules and four sensitive markers, with the four fixed denial texts byte-identical — `.kernel_vault` is always denied; `shared_readonly/` rejects file writes and shell redirection; cross-slot access is denied (`../slot_*`, or one command referencing two `worktrees/slot_*`).

Full parameters and defaults live in section 6 and in `greatwall-agent/bin/gw_mcp_server.py` (`TOOLS_SCHEMA`).

---

## 3. Host capability mapping (Antigravity → DSH)

| Capability | Antigravity implementation | This package on DSH | Code |
| :--- | :--- | :--- | :--- |
| MCP stdio registration | `mcp_config.json` (absolute paths to `python.exe` and the script) | `lib/index.js` mounts `@deepseek-ai/dsh-mcp-client` over stdio inside `apply()`; the script path resolves from `import.meta.url` | [`lib/index.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/index.js) |
| Skill delivery | `skills/greatwall-campaign/SKILL.md` on disk | `ctx.skills.register()` at runtime; body = original text **verbatim** plus one prepended tool-name mapping note | [`lib/skillpack.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/skillpack.js), [`lib/index.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/index.js) |
| Clean-room gate | `hooks.json` `PreToolUse` + `bin/hook_gate.py` (stdin JSON → `{"decision":"deny"}`) | `ctx.tools.guard(execution => reason \| undefined)`, same three rules | [`lib/gate.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/gate.js) |
| Standing rules | `rules/AGENTS.md` | **Not auto-loaded**; shipped unchanged, copy it into the campaign workspace or global rules | [`greatwall-agent/rules/AGENTS.md`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/greatwall-agent/rules/AGENTS.md) |
| Sub-agents | `agents/gw-*.md` named sub-agent manifests | **Not auto-registered** (DSH has no equivalent named sub-agent registry); the three prompts ship unchanged for manual reuse | [`greatwall-agent/agents/`](https://github.com/Qingzhu093/dsh-greatwall-agent/tree/main/greatwall-agent/agents) |

> The last two are **deliberately not runtime features**, not omissions. See section 10.

---

## 4. Installation

### 4.1 Choose a channel first

| Situation | Channel | Note |
| :--- | :--- | :--- |
| DSH Desktop (Electron-managed profile, e.g. `desktop`) | The DSH Desktop plugin manager | The CLI cannot manage Electron-managed profiles |
| CLI-managed profile | `dsh plugin --profile <name> add ...` | Requires a dsh CLI that satisfies `engines.dsh`, and pnpm on `PATH` |
| Plugin market | Add an index source in the Discover tab | Index file: [`market/index.json`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/market/index.json); needs hosting before use |

### 4.2 DSH Desktop (the path verified on 2026-11-07)

After installing the local directory through the DSH Desktop plugin manager, the profile manifest records a `link:` dependency and appends the package to the bundle list. The actual record in `C:\Users\wangy\.dsh\profiles\desktop\package.json` on this machine:

```json
"dependencies": {
  "dsh-greatwall-agent": "link:D:/Documents/deepseek harness/长城Agent_框架设计/plugins/dsh-greatwall-agent"
},
"dsh": {
  "profile": {
    "bundles": [
      "...",
      "dsh-greatwall-agent"
    ]
  }
}
```

> Measured: `dsh plugin --profile desktop ...` is refused with
> `error: profile "desktop" is managed exclusively by the Electron application`.
> Use the in-app plugin manager for Electron-managed profiles; do not hand-edit the profile.

### 4.3 CLI-managed profile (npm package, after publishing)

```powershell
dsh plugin --profile <profile-name> add dsh-greatwall-agent
```

- `dsh plugin` **forwards its arguments to pnpm**, so pnpm must be on `PATH`; on this machine it fails with `'pnpm' is not recognized as an internal or external command`.
- The first use initializes the profile (with `@deepseek-ai/dsh-base` as its first bundle, per the official docs).
- Inspect the composed layer with `dsh --profile <profile-name> --dump-config`.

### 4.4 CLI-managed profile (local directory, linked)

```powershell
dsh plugin --profile <profile-name> add 'D:\Documents\deepseek harness\长城Agent_框架设计\plugins\dsh-greatwall-agent'
```

The single quotes matter in PowerShell 7 because the path contains a space.

### 4.5 Tarball

```powershell
Set-Location 'plugins\dsh-greatwall-agent'
npm pack
dsh plugin --profile <profile-name> add '.\dsh-greatwall-agent-4.2.0.tgz'
```

### 4.6 Plugin market index (after publishing)

[`market/index.json`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/market/index.json) in the source package directory is a `format: 1` DSH market index (with `icons/`). `market/` is not part of the npm tarball's `files` whitelist: it is served as static files from the repository. Before publishing, replace the placeholder `"publishTimestamp": "__PUBLISH_TIMESTAMP__"` with the real Unix seconds and host `market/index.json` together with `market/icons/`.

Planned hosting URL (**not published yet; unverified**):

```text
https://qingzhu093.github.io/dsh-greatwall-agent/market/index.json
```

In DSH (official flow): **Plugins → More beside Experimental plugins → turn on Custom plugin markets → Discover → Add index source**, paste the index URL, then install from the card. DSH ships no central market; the publisher hosts the index.

---

## 5. Quick start

1. **Prepare data**: put public datasets under `<workspace>/shared_readonly/datasets_public/` (the original runbook's Step 0.1 convention).
2. **Initialize the workspace** (Phase 0, step 1):

```text
mcp__greatwall-agent__gw_init_campaign
{
  "workspaceRoot": "D:\\campaigns\\cumcm-2026-b",
  "taskId": "CUMCM_2026_B",
  "taskDescription": "task goal and hard boundaries...",
  "domainType": "ALGO_COMPETITION",
  "primaryMetric": "RMSLE",
  "higherIsBetter": false
}
```

3. **Distill and mint `s_0`** (Phase 0, step 2): `mcp__greatwall-agent__gw_lock_distillation` with 2–4 `orthogonalFamilies` and either `anchorBaselineCode` or `candidateBaselines`.
4. **Run the clean-room loop** (Phases 1 & 2): `gw_allocate_slot` → `gw_surgical_replace` → `gw_evaluate_slot` → `gw_submit_legacy`.
5. **Plateau / 60 steps** (Phase 3): `gw_lineage_control(action="submit_reflection")` files the 3-turn contract; use `gw_archive_query` for the L0 index.
6. **Final delivery** (Phase 4): structural synthesis via `gw_archive_query(action="get_l0_index")`, then `gw_compile_delivery` to build `final_delivery/`.

The full four-phase runbook is the bundled **`greatwall-campaign`** skill (body = the original `SKILL.md`). It appears in the DSH session skill catalog (confirmed during install verification).

| Phase | Primary tools |
| :--- | :--- |
| Phase 0 pre-flight and opening distillation | `gw_init_campaign`, `gw_lock_distillation` |
| Phases 1 & 2 clean-room slots and surgical replacement | `gw_allocate_slot`, `gw_surgical_replace`, `gw_evaluate_slot`, `gw_submit_legacy` |
| Phase 3 60-step reflection chamber and taste calibration | `gw_lineage_control`, `gw_archive_query` |
| Phase 4 structural synthesis and final delivery | `gw_archive_query`, `gw_compile_delivery` |

---

## 6. The nine tools

The Antigravity plugin registered the bare names `gw_*`; through the official DSH MCP bridge the model-facing names become `mcp__greatwall-agent__<original name>`.

| Original name | Model-facing name | Phase | Required arguments | Purpose |
| :--- | :--- | :---: | :--- | :--- |
| `gw_init_campaign` | `mcp__greatwall-agent__gw_init_campaign` | Phase 0 | `workspaceRoot`, `taskId`, `taskDescription` | Creates `.kernel_vault/`, `shared_readonly/archive`, `worktrees/`; runs the EDA probe and locks `task_config.yaml` |
| `gw_lock_distillation` | `mcp__greatwall-agent__gw_lock_distillation` | Phase 0 | `workspaceRoot`, `orthogonalFamilies` | Locks the distillation contract; runs candidates in the sandbox and locks `s_0` |
| `gw_allocate_slot` | `mcp__greatwall-agent__gw_allocate_slot` | Phases 1 & 2 | `workspaceRoot`, `familyId`, `targetedCodeBlock`, `hypothesis` | Allocates a git-free island and writes `scoped_brief.md` (with `BarrierProof` blocking) |
| `gw_surgical_replace` | `mcp__greatwall-agent__gw_surgical_replace` | Phases 1 & 2 | `workspaceRoot`, `slotId`, `targetBlockName`, `newBlockCode` | AST in-place replacement of a function/class/method; writes `legacy_out/diff.patch` |
| `gw_evaluate_slot` | `mcp__greatwall-agent__gw_evaluate_slot` | Phases 1 & 2 | `workspaceRoot`, `slotId` | Isolated evaluation + static audit + HMAC receipt + four-way triage |
| `gw_submit_legacy` | `mcp__greatwall-agent__gw_submit_legacy` | Phases 1 & 2 | `workspaceRoot`, `slotId` | Accepts the five-item legacy pack, archives primitives, reclaims the island |
| `gw_lineage_control` | `mcp__greatwall-agent__gw_lineage_control` | Phase 3 | `workspaceRoot`, `action` | `soft_flush` / `hard_fork` / `submit_reflection` / `differential_test` / `deprecate_errata` |
| `gw_archive_query` | `mcp__greatwall-agent__gw_archive_query` | Phases 3 & 4 | `workspaceRoot`, `action` | `get_l0_index` / `get_l2_item` / `get_campaign_status` / `retract_claim` |
| `gw_compile_delivery` | `mcp__greatwall-agent__gw_compile_delivery` | Phase 4 | `workspaceRoot`, `executiveSummaryMd` | Anti-bluff audit and `final_delivery/` envelope |

Key defaults (from `TOOLS_SCHEMA` and `handle_tool_call`):

| Argument | Default | Note |
| :--- | :--- | :--- |
| `domainType` | `ALGO_COMPETITION` | also `FORMAL_MATH` / `PHYSICS_SIM` / `BIO_CHEM` |
| `primaryMetric` | `"score"` | — |
| `higherIsBetter` | `true` | pass `false` for error/latency metrics |
| `maxConcurrentSlots` | `4` | — |
| `totalStepBudget` | `240` | used for stage pressure |
| `stepBudget` | `25` | per-node step quota |
| `relScriptPath` / `entryScript` | `src/main.py` | relative to the island |
| `timeoutSec` | `120` | evaluation execution timeout; the MCP call timeout is 600 s (section 7) |
| `stepsConsumed` | `15` | cumulative 60-step commitment lock |
| `enforceDataCompleteness` | `false` | force-block missing `A_data` multimodal files |

> Note: the bundled skill body (the original `SKILL.md`) says "8 native tools" and covers only 8 of the 9 above; `gw_lineage_control` is documented in its MCP tool description. That wording is inherited from the original and was not edited, by design.

---

## 7. Configuration

| Field | Type | Default | Meaning |
| :--- | :--- | :--- | :--- |
| `pythonPath` | string | `python` on Windows, `python3` elsewhere | Interpreter used for `gw_mcp_server.py`; use an absolute path for virtualenvs or multiple Pythons |
| `cleanroomGate` | boolean | `true` | Installs the clean-room tool guard; `false` registers nothing |

Override by patch id `greatwall-agent` in the profile's own `cordis.patch.yml` (the `config` object **replaces** the whole value, it is not deep-merged, so restate both fields):

```yaml
- id: greatwall-agent
  name: 'dsh-greatwall-agent'
  config:
    pythonPath: 'C:\Users\wangy\AppData\Local\Programs\Python\Python314\python.exe'
    cleanroomGate: true
```

This package's bundle layer contains a single `insert` row (`id: greatwall-agent`, `name: dsh-greatwall-agent`) and **deliberately no `config` block**: defaults live only in the Schemastery `Config` in `lib/index.js`, so they cannot drift.

---

## 8. Requirements

| Item | Requirement | Evidence |
| :--- | :--- | :--- |
| DSH | `>=0.2.2-rc.1 <0.3.0-0` | `package.json` `engines.dsh`; checked at install and startup |
| Node.js | `^22.19.0 \|\| >=24.0.0` | `engines.node`; tested with `v24.20.0` |
| Python | 3.x, standard library only | tested with `3.14.7`; imports are stdlib only (`ast/csv/ctypes/difflib/gc/hashlib/hmac/importlib/io/json/os/random/re/shutil/stat/subprocess/sys/textwrap/time/traceback/uuid`, ...) |
| Platform | Windows verified (Windows Job Object process-tree kill) | `greatwall-agent/tests/test_plugin_e2e.py`, test_09; macOS/Linux untested |
| Network | not needed at runtime (local stdio) | DSH spawns the MCP child locally |

DSH peers (provided by the installed DSH): `@deepseek-ai/dsh-mcp-client` (`>=0.2.2-rc.1 <0.3.0-0`), `@deepseek-ai/schemastery` (`~3.19.0`), `@deepseek-ai/cordis` (`~4.1.0`, optional).

> Note: the standalone `dsh` CLI on this machine reports `0.1.5-rc.1`, which does **not** satisfy `engines.dsh`. The 2026-11-07 verification was performed in the DSH Desktop `desktop` profile running DSH `0.2.2-rc.1`. Check the CLI version before installing from a CLI.

---

## 9. Verified / not verified

### 9.1 Verified (2026-11-07, `desktop` profile)

| Evidence | Result |
| :--- | :--- |
| Install record | `dsh-greatwall-agent` is a `link:` dependency in the `desktop` profile and is listed in `dsh.profile.bundles` |
| Config entry | `Config.listConfigs` returns `id: include:greatwall-agent`, `patchId: greatwall-agent`, `status: schema`, `acceptsMissing: true`, defaults `pythonPath=python`, `cleanroomGate=true` |
| Nine tools | `Tool.listTools` lists every `mcp__greatwall-agent__gw_*` tool |
| MCP bridge connected | `list_mcp_resources(server="greatwall-agent")` returns `{"resources":[]}` (tools-only server; a reply proves the stdio bridge is up) |
| MCP protocol | manual stdio probe: `initialize` → `{"protocolVersion":"2024-11-05","serverInfo":{"name":"greatwall-agent","version":"4.2.0"},"capabilities":{"tools":{}}}`; `tools/list` → 9 tools |
| Verbatim core | `node tools/verify-core.mjs` → `OK: 18 core files match core-manifest.sha256 (byte-identical Antigravity tree)` |
| End-to-end suite | 10/10 pass: this round `Ran 10 tests in 2.882s / OK`; archived log [`docs/audit/e2e_run.log`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/docs/audit/e2e_run.log) recorded `2.990s` |
| Gate live | `.kernel_vault` read, `shared_readonly` shell redirection, `../slot_*`, and two slots in one command are all denied (texts below); ordinary commands pass |
| Environment | DSH `0.2.2-rc.1`, Node `24.20.0`, Python `3.14.7` (install record; node/python re-checked locally) |

The four fixed denial texts (byte-identical to `greatwall-agent/bin/hook_gate.py`):

```text
🔒 [长城 Agent 清洁室隔离门禁] 严禁直接读取或修改 `.kernel_vault` 内核保险箱（含评测真值与 HMAC 密钥）！请使用 `gw_*` 标准 MCP 工具交互。
🔒 [长城 Agent 只读档案馆门禁] 严禁通过终端命令重定向或修改 `shared_readonly/` 公共只读区！
🔒 [长城 Agent 只读档案馆门禁] `shared_readonly/` 为公共只读挂载区，严禁直接用写文件工具篡改！请在孤岛 `legacy_out/` 下提交遗产包并通过 `gw_submit_legacy` 验收入库。
🔒 [长城 Agent 跨孤岛防偷看门禁] 严禁通过 `../slot_*` 越界访问其他并行探索槽位的私有目录！
```

### 9.2 Not verified (do not treat as guaranteed)

- **Non-Windows platforms**: the `python3` default, path jail and isolated evaluation are untested there; Windows Job Object capabilities do not apply.
- **Outside the DSH version range**: `<0.2.2-rc.1` and `>=0.3.0-0` are refused by `engines`; their degraded behaviour was not measured.
- **npm publish and market hosting**: the GitHub repo, npm package and GitHub Pages index URL are not published; `market/index.json` still carries the `publishTimestamp` placeholder, and the release task owns the publish flow.
- **Skill visibility inside a session**: `greatwall-campaign` was confirmed usable during install verification; this documentation session cannot enumerate the skill catalog from the tool side and did not re-check it.
- **Other Python versions / virtualenvs**: only Python `3.14.7` was tested.

---

## 10. Known limitations (deliberately not ported)

1. **`rules/AGENTS.md` is not auto-loaded.** DSH has no plugin-level standing-rule injection point; copy it into the campaign workspace (or merge it into global rules) as the original instructions say.
2. **`agents/*.md` are not auto-registered.** DSH has no Antigravity-style named sub-agent registry; the three prompts ship unchanged as material you can paste into a sub-agent prompt.
3. **The skill body is the original text.** Apart from one prepended tool-name mapping note it is not edited, so the original "8 native tools" wording and the missing `gw_lineage_control` coverage are preserved.
4. **`mcp_config.json` ships unchanged but is not read.** It contains the original machine's absolute paths (`C:\Users\wangy\...`); on DSH the path is resolved dynamically by `lib/index.js`.
5. **The gate can only deny, never allow or rewrite.** `ctx.tools.guard` runs after pre-execute policy and approval and is a monotonic denial; it does not replace DSH approval or sandboxing.
6. **Hard dependency on the `tools` service.** The plugin declares `inject = ['tools']`; a host without a tool registry does not activate it (nor the MCP bridge or skill).
7. **600 s per MCP call.** `toolCallTimeoutMs: 600000` is deliberately generous for `gw_evaluate_slot`; longer runs must be split inside the tool.

---

## 11. Package layout

```text
dsh-greatwall-agent/
├── package.json                  # npm manifest: engines, dsh.bundle, peerDependencies, files, scripts (prepack/verify:core/manifest:core)
├── cordis.patch.yml              # bundle layer: one insert row (id: greatwall-agent)
├── lib/
│   ├── index.js                  # host entry: mount MCP, register skill, install gate
│   ├── gate.js                   # clean-room gate (hook_gate.py rules + host field adapter)
│   └── skillpack.js              # read/validate SKILL.md and register into ctx.skills
├── locale/{zh,en}.json           # market/settings title and description
├── icon.svg                      # plugin icon
├── tools/
│   ├── clean-pycache.mjs         # prepack: remove __pycache__/*.pyc so caches never enter the tarball
│   ├── make-core-manifest.mjs    # regenerate core-manifest.sha256
│   └── verify-core.mjs           # assert the greatwall-agent/ tree matches the manifest
├── core-manifest.sha256          # SHA-256 of the 18 core files
├── greatwall-agent/              # original Antigravity plugin tree (byte-identical, 18 files)
│   ├── bin/{gw_mcp_server.py,hook_gate.py}
│   ├── lib/{sandbox,archive,evaluator,engine}.py
│   ├── skills/greatwall-campaign/SKILL.md
│   ├── rules/AGENTS.md
│   ├── agents/{gw-distiller,gw-explorer,gw-auditor}.md
│   ├── tests/test_plugin_e2e.py
│   └── plugin.json / mcp_config.json / hooks.json / README.md / assets/logo.svg
├── market/index.json             # DSH market index (format 1; timestamp placeholder before publish)
├── .release/verify-index.mjs     # offline market-index validator
├── docs/{INSTALL,ARCHITECTURE}.md
└── docs/BUG_REPORT.md            # unified defect report for the original Python core (generated this round; section 13)
```

---

## 12. Verification and tests (maintainers)

```powershell
# 0) from the design-repo root
Set-Location 'D:\Documents\deepseek harness\长城Agent_框架设计'

# 1) verbatim-core check: expect OK: 18 core files match ...
node 'plugins\dsh-greatwall-agent\tools\verify-core.mjs'

# 2) ten end-to-end acceptance tests (zero third-party deps, ~3 s)
$env:PYTHONUTF8 = '1'
python -W default 'plugins\dsh-greatwall-agent\greatwall-agent\tests\test_plugin_e2e.py'

# 3) offline market-index validation (warns while the timestamp placeholder remains; --strict for publish)
node 'plugins\dsh-greatwall-agent\.release\verify-index.mjs'
```

The package also exposes `npm run verify:core` and `npm run manifest:core` (run from the package directory). `npm pack` / `npm publish` run `prepack` → `node tools/clean-pycache.mjs`, which removes `__pycache__` and `*.pyc` under `greatwall-agent/`; the MCP child also sets `PYTHONDONTWRITEBYTECODE=1` so caches are not recreated inside an installed package.

---

## 13. Docs and defects

- Install, verification, troubleshooting, uninstall: [`docs/INSTALL.md`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/docs/INSTALL.md)
- File-by-file port architecture: [`docs/ARCHITECTURE.md`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/docs/ARCHITECTURE.md)
- Chinese README: [`README.md`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/README.md)
- Unified defect report for the original Python core: [`docs/BUG_REPORT.md`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/docs/BUG_REPORT.md) (see BUG_REPORT.md, generated this round)
- Design-repo archive (physical locations, release and maintenance commands): `17_长城Agent_V4-DSH插件移植档案.md` (design-repo root)

> This plugin reports core defects instead of fixing them: touching `greatwall-agent/` immediately fails `verify-core.mjs`. File any kernel issue in [`docs/BUG_REPORT.md`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/docs/BUG_REPORT.md); never edit `greatwall-agent/` in place.

---

## 14. License

MIT, see [`LICENSE`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/LICENSE). The original `greatwall-agent` plugin is redistributed under the same MIT licence, copyright Great Wall Agent Contributors.
