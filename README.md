# 长城 Agent V4.2 — DeepSeek Harness 插件（`dsh-greatwall-agent`）

> **一句话定位**：把 Google Antigravity 版 `greatwall-agent` 的长程无人值守科研 / 算法竞赛攻关能力搬进 **DeepSeek Harness（DSH）**——**Python 内核逐字节不改**，只重写宿主适配层：MCP 桥、技能注册与清洁室门禁。

| 项目 | 值 |
| :--- | :--- |
| npm 包名 | `dsh-greatwall-agent` |
| 版本 | `4.2.0` |
| DSH 版本要求 | `>=0.2.2-rc.1 <0.3.0-0`（`package.json` 的 `engines.dsh`） |
| Node 要求 | `^22.19.0 \|\| >=24.0.0`（`engines.node`） |
| 许可证 | MIT（[`LICENSE`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/LICENSE)） |
| 源码仓库 | <https://github.com/Qingzhu093/dsh-greatwall-agent>（发布后生效） |
| 原 Antigravity 插件 | 设计仓库 `plugins/greatwall-agent/`（只读，本包 `greatwall-agent/` 为其逐字节副本） |

---

## 一、这是什么

原 Antigravity 插件由两层组成：

- **跨平台内核**：`lib/*.py` + `bin/gw_mcp_server.py` + `bin/hook_gate.py`，纯 Python 标准库实现；
- **Antigravity 宿主薄壳**：`plugin.json`、`mcp_config.json`、`hooks.json`、`skills/`、`rules/`、`agents/`。

DSH 的宿主契约与 Antigravity 不同，因此本包做了两件事：

1. 把**原插件树整棵逐字节复制**到包内 [`greatwall-agent/`](https://github.com/Qingzhu093/dsh-greatwall-agent/tree/main/greatwall-agent)，并用 `core-manifest.sha256`（18 个文件）把“未改一行代码”变成可机器校验的事实；
2. 用 [`lib/index.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/index.js)、[`lib/gate.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/gate.js)、[`lib/skillpack.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/skillpack.js) 重新实现三项宿主能力：MCP 服务挂载、技能注册、清洁室工具守卫。

因此你拿到的不是“行为近似”的改写版，而是**同一份内核 + 一层新的宿主适配**。内核工具的参数、返回值与裁决逻辑与原插件一致。

---

## 二、核心特性

1. **Phase 0 开局先蒸馏**（`gw_init_campaign` + `gw_lock_distillation`）：确定性 EDA 数据探针、锁定消歧结论、固化正交方法族 / 过时模型黑名单 / 调库边界清单，并在沙箱实跑 M 个候选基线、择优铸造零号强基线 `s_0`。
2. **无 `.git` 清洁室孤岛**（`gw_allocate_slot` + `gw_surgical_replace`）：从内核快照检出孤岛目录，自动装配 L1 `scoped_brief.md`；用 AST 原位热插拔替换单一目标代码块 `c_t`，拒绝全量重写。
3. **跨进程防作弊评测**（`gw_evaluate_slot`）：AST 反作弊 / 过时模型 / 手搓轮子 / 多模态完整性 / 结构改动率对账，四元组剥皮查新与同构扰动，输出带 HMAC-SHA256 签名的 `metrics_receipt.json` 与四级分诊。
4. **零向量 L0/L1/L2 档案馆**（`gw_submit_legacy` + `gw_archive_query`）：五件套遗产验收、原语沙箱单测、`PRIMITIVES_API.md` 签名自动提取、跨血统引用计数、错误结论依赖树撤回。
5. **谱系控制与 60 步内省室**（`gw_lineage_control`）：原地软清栈、祖先硬分叉、3 轮内省契约、跨分支差分互测、错题热勘误追溯平反。
6. **终局防吹牛五件套**（`gw_compile_delivery`）：拦截 `TODO / TBD / Conclusions Here` 占位符，分数对比表强制从 HMAC 收据硬绑定，一键生成 `final_delivery/`。
7. **清洁室门禁**（原 `PreToolUse` 钩子的 DSH 移植）：三条规则、四类敏感标记，四条固定拒绝文案与原脚本逐字节一致——`.kernel_vault` 一律拒绝；`shared_readonly/` 禁止文件写入与终端重定向；禁止跨槽位访问（`../slot_*` 或单条命令引用两个 `worktrees/slot_*`）。

工具的完整参数与默认值见[第六节](#六9-个工具名对照表)与 `greatwall-agent/bin/gw_mcp_server.py` 的 `TOOLS_SCHEMA`。

---

## 三、宿主能力映射（Antigravity → DSH）

| 能力 | Antigravity 原实现 | 本包的 DSH 实现 | 代码位置 |
| :--- | :--- | :--- | :--- |
| MCP stdio 服务注册 | `mcp_config.json`（内含 `python.exe` 与脚本的**绝对路径**） | 由 `lib/index.js` 在 `apply()` 中 `ctx.plugin(@deepseek-ai/dsh-mcp-client)` 以 stdio 挂载；脚本路径从 `import.meta.url` 解析 | [`lib/index.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/index.js) |
| 技能交付 | `skills/greatwall-campaign/SKILL.md` 磁盘目录 | `ctx.skills.register()` 运行时注册；正文 = 原文 **逐字** + 仅前置一段工具名映射注记 | [`lib/skillpack.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/skillpack.js)、[`lib/index.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/index.js) |
| 清洁室门禁 | `hooks.json` 的 `PreToolUse` + `bin/hook_gate.py`（stdin JSON → `{"decision":"deny"}`） | `ctx.tools.guard(execution => reason \| undefined)`，三条规则同源移植 | [`lib/gate.js`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/lib/gate.js) |
| 常驻规则 | `rules/AGENTS.md` | **不自动装载**；原文件随包提供，按原说明复制到攻关工作区或全局规则 | [`greatwall-agent/rules/AGENTS.md`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/greatwall-agent/rules/AGENTS.md) |
| 子智能体 | `agents/gw-*.md` 命名子智能体清单 | **不自动注册**（DSH 没有 Antigravity 那种命名子智能体注册表）；三份提示词原样随包，可人工复用 | [`greatwall-agent/agents/`](https://github.com/Qingzhu093/dsh-greatwall-agent/tree/main/greatwall-agent/agents) |

> 后两项是**刻意不迁移为运行时特性**，不是遗漏。详见[第十节](#十已知限制刻意未迁移)。

---

## 四、安装

### 4.1 先选安装通道

| 场景 | 推荐通道 | 说明 |
| :--- | :--- | :--- |
| DSH Desktop（Electron 托管 profile，如本机 `desktop`） | DSH Desktop 的插件管理页面 | CLI 无法管理 Electron 托管 profile |
| 自建 CLI profile（`dsh plugin` 管理） | `dsh plugin --profile <name> add ...` | 需要 dsh CLI 版本满足 `engines.dsh`，且 PATH 中有 pnpm |
| 插件市场 | Discover 页添加索引源 | 索引文件见 [`market/index.json`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/market/index.json)，托管后才能添加 |

### 4.2 DSH Desktop（2026-11-07 本机已验证的方式）

在 DSH Desktop 的插件管理入口安装本地目录后，profile 清单会写入一条 `link:` 依赖并把包名追加进 bundle 列表。本机 `C:\Users\wangy\.dsh\profiles\desktop\package.json` 中的实际记录：

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

> 实测：`dsh plugin --profile desktop ...` 会被拒绝，报
> `error: profile "desktop" is managed exclusively by the Electron application`。
> Electron 托管 profile 请使用应用内插件管理，不要手改 profile。

### 4.3 CLI 托管 profile（npm 包，发布后可用）

```powershell
dsh plugin --profile <profile-name> add dsh-greatwall-agent
```

- `dsh plugin` 把参数**转发给 pnpm**，所以 PATH 中必须有 pnpm；本机实测缺 pnpm 时报 `'pnpm' is not recognized as an internal or external command`。
- 首次使用会初始化该 profile（以 `@deepseek-ai/dsh-base` 为首个 bundle，官方文档口径）。
- 安装后检查组合层：`dsh --profile <profile-name> --dump-config`。

### 4.4 CLI 托管 profile（本地目录，直接 link 本仓库）

```powershell
dsh plugin --profile <profile-name> add 'D:\Documents\deepseek harness\长城Agent_框架设计\plugins\dsh-greatwall-agent'
```

PowerShell 7 中路径含空格，单引号不可省略。

### 4.5 tarball 安装

```powershell
Set-Location 'plugins\dsh-greatwall-agent'
npm pack
dsh plugin --profile <profile-name> add '.\dsh-greatwall-agent-4.2.0.tgz'
```

### 4.6 插件市场索引（发布后）

源码包目录中的 [`market/index.json`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/market/index.json) 是 `format: 1` 的 DSH 插件市场索引（含 `icons/` 图标）。`market/` 不在 npm tarball 的 `files` 白名单内，发布时从仓库作为静态文件托管；发布流程需要先把占位符 `"publishTimestamp": "__PUBLISH_TIMESTAMP__"` 换成真实 Unix 秒，再把 `market/index.json` 与 `market/icons/` 一起托管。

计划的托管地址（**本轮尚未发布，未验证可访问**）：

```text
https://qingzhu093.github.io/dsh-greatwall-agent/market/index.json
```

在 DSH 中使用（官方文档流程）：**Plugins → Experimental plugins 旁的 More → 打开 Custom plugin markets → Discover → Add index source**，填入上面的索引 URL，再在卡片上安装。DSH 不自带中心市场，索引必须由发布方自行托管。

---

## 五、快速开始

1. **准备数据**：把公开数据集放到 `<workspace>/shared_readonly/datasets_public/`（原 Runbook Step 0.1 的目录约定）。
2. **初始化工作区**（Phase 0 第一步）：

```text
mcp__greatwall-agent__gw_init_campaign
{
  "workspaceRoot": "D:\\campaigns\\cumcm-2026-b",
  "taskId": "CUMCM_2026_B",
  "taskDescription": "题面目标与硬性边界……",
  "domainType": "ALGO_COMPETITION",
  "primaryMetric": "RMSLE",
  "higherIsBetter": false
}
```

3. **蒸馏并铸造 `s_0`**（Phase 0 第二步）：`mcp__greatwall-agent__gw_lock_distillation`，传入 2~4 个 `orthogonalFamilies` 与 `anchorBaselineCode`（或 `candidateBaselines` 竞技择优）。
4. **进入清洁室循环**（Phase 1&2）：`gw_allocate_slot` → `gw_surgical_replace` → `gw_evaluate_slot` → `gw_submit_legacy`。
5. **平台期 / 满 60 步**（Phase 3）：`gw_lineage_control(action="submit_reflection")` 提交 3 轮内省契约；用 `gw_archive_query` 查阅 L0 索引。
6. **终局交付**（Phase 4）：`gw_archive_query(action="get_l0_index")` 做跨分支结构拼图，最后 `gw_compile_delivery` 生成 `final_delivery/`。

完整的四阶段作业手册由随包技能 **`greatwall-campaign`** 提供（正文即原 `SKILL.md`）；技能会在 DSH 会话技能目录中出现（安装验证时已确认可用）。

| 阶段 | 主用工具 |
| :--- | :--- |
| Phase 0 开局前置消歧与先蒸馏 | `gw_init_campaign`、`gw_lock_distillation` |
| Phase 1&2 清洁室孤岛并发深耕与微创手术 | `gw_allocate_slot`、`gw_surgical_replace`、`gw_evaluate_slot`、`gw_submit_legacy` |
| Phase 3 60 步原位内省室与品味校准 | `gw_lineage_control`、`gw_archive_query` |
| Phase 4 跨分支结构拼图与终局五件套 | `gw_archive_query`、`gw_compile_delivery` |

---

## 六、9 个工具名对照表

原 Antigravity 版按裸名 `gw_*` 注册；经 DSH 官方 MCP 桥后，模型侧公开名统一为 `mcp__greatwall-agent__<原始名>`。

| 原始工具名 | 模型侧公开名 | 阶段 | 必填参数 | 作用 |
| :--- | :--- | :---: | :--- | :--- |
| `gw_init_campaign` | `mcp__greatwall-agent__gw_init_campaign` | Phase 0 | `workspaceRoot`, `taskId`, `taskDescription` | 建 `.kernel_vault/`、`shared_readonly/archive`、`worktrees/` 目录树；跑 EDA 探针并锁定 `task_config.yaml` |
| `gw_lock_distillation` | `mcp__greatwall-agent__gw_lock_distillation` | Phase 0 | `workspaceRoot`, `orthogonalFamilies` | 固化蒸馏四件套；沙箱实跑候选基线并锁定 `s_0` |
| `gw_allocate_slot` | `mcp__greatwall-agent__gw_allocate_slot` | Phase 1&2 | `workspaceRoot`, `familyId`, `targetedCodeBlock`, `hypothesis` | 分配无 `.git` 孤岛并生成 `scoped_brief.md`（含 `BarrierProof` 拦截） |
| `gw_surgical_replace` | `mcp__greatwall-agent__gw_surgical_replace` | Phase 1&2 | `workspaceRoot`, `slotId`, `targetBlockName`, `newBlockCode` | AST 原位替换函数/类/方法，生成 `legacy_out/diff.patch` |
| `gw_evaluate_slot` | `mcp__greatwall-agent__gw_evaluate_slot` | Phase 1&2 | `workspaceRoot`, `slotId` | 跨进程隔离评测 + 静态审计 + HMAC 成绩单 + 四级分诊 |
| `gw_submit_legacy` | `mcp__greatwall-agent__gw_submit_legacy` | Phase 1&2 | `workspaceRoot`, `slotId` | 验收五件套遗产包、入库原语、回收孤岛 |
| `gw_lineage_control` | `mcp__greatwall-agent__gw_lineage_control` | Phase 3 | `workspaceRoot`, `action` | `soft_flush` / `hard_fork` / `submit_reflection` / `differential_test` / `deprecate_errata` |
| `gw_archive_query` | `mcp__greatwall-agent__gw_archive_query` | Phase 3&4 | `workspaceRoot`, `action` | `get_l0_index` / `get_l2_item` / `get_campaign_status` / `retract_claim` |
| `gw_compile_delivery` | `mcp__greatwall-agent__gw_compile_delivery` | Phase 4 | `workspaceRoot`, `executiveSummaryMd` | 终局防吹牛审计并生成 `final_delivery/` 五件套 |

主要默认值（以 MCP `TOOLS_SCHEMA` 与 `handle_tool_call` 为准）：

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `domainType` | `ALGO_COMPETITION` | 可选 `FORMAL_MATH` / `PHYSICS_SIM` / `BIO_CHEM` |
| `primaryMetric` | `"score"` | — |
| `higherIsBetter` | `true` | 误差/耗时类指标传 `false` |
| `maxConcurrentSlots` | `4` | — |
| `totalStepBudget` | `240` | 阶段压力计算 |
| `stepBudget` | `25` | 单节点步数配额 |
| `relScriptPath` / `entryScript` | `src/main.py` | 孤岛内相对路径 |
| `timeoutSec` | `120` | 仅评测执行超时；MCP 侧单次调用超时为 600 秒，见[第七节](#七配置) |
| `stepsConsumed` | `15` | 累计 60 步深挖锁 |
| `enforceDataCompleteness` | `false` | 强制拦截遗漏 `A_data` 多模态文件 |

> 注：随包技能正文（原 `SKILL.md` 原文）写的是“8 个原生工具”，只覆盖了上述 9 个中的 8 个；`gw_lineage_control` 的完整说明见 MCP 工具描述。这是原文既有的表述，本包按“逐字节不改”原则未修正。

---

## 七、配置

| 字段 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `pythonPath` | string | Windows：`python`；其他平台：`python3` | 运行 `gw_mcp_server.py` 的解释器路径；虚拟环境/多版本 Python 时改成绝对路径 |
| `cleanroomGate` | boolean | `true` | 是否安装清洁室工具守卫；`false` 时完全不注册 |

覆盖方式：在 profile 自己的 `cordis.patch.yml` 里按 patch id `greatwall-agent` 覆盖整行（`config` 是**整体替换**，不是深合并，所以两个字段都要写全）：

```yaml
- id: greatwall-agent
  name: 'dsh-greatwall-agent'
  config:
    pythonPath: 'C:\Users\wangy\AppData\Local\Programs\Python\Python314\python.exe'
    cleanroomGate: true
```

`cordis.patch.yml` 中本包的 bundle 层只有一行 `insert`（`id: greatwall-agent` / `name: dsh-greatwall-agent`），**故意不写 `config`**：默认值只存在于 `lib/index.js` 的 Schemastery `Config` 里，避免两处默认值漂移。

---

## 八、运行要求

| 项 | 要求 | 依据 |
| :--- | :--- | :--- |
| DSH | `>=0.2.2-rc.1 <0.3.0-0` | `package.json` `engines.dsh`；安装与启动会校验 |
| Node.js | `^22.19.0 \|\| >=24.0.0` | `engines.node`；本机实测 `v24.20.0` |
| Python | 3.x（纯标准库，无第三方依赖） | 本机实测 `3.14.7`；导入表仅 `ast/csv/ctypes/difflib/gc/hashlib/hmac/importlib/io/json/os/random/re/shutil/stat/subprocess/sys/textwrap/time/traceback/uuid` 等标准库 |
| 平台 | Windows 实测通过（Windows Job Object 进程树强杀） | 见 `greatwall-agent/tests/test_plugin_e2e.py` 的 test_09；macOS/Linux 未实测 |
| 网络 | 运行期不需要（本地 stdio） | MCP 子进程由 DSH 本地拉起 |

DSH 依赖（`peerDependencies`，由安装的 DSH 提供）：`@deepseek-ai/dsh-mcp-client`（`>=0.2.2-rc.1 <0.3.0-0`）、`@deepseek-ai/schemastery`（`~3.19.0`）、`@deepseek-ai/cordis`（`~4.1.0`，optional）。

> 注意：本机 PATH 上的独立 `dsh` CLI 自报 `0.1.5-rc.1`，**不满足**本包 `engines.dsh`；2026-11-07 的安装验证是在 DSH Desktop（DSH `0.2.2-rc.1`）的 `desktop` profile 中完成的。用 CLI 安装前先确认 CLI 版本。

---

## 九、已验证 / 未验证

### 9.1 已验证（2026-11-07，`desktop` profile）

| 证据 | 结果 |
| :--- | :--- |
| 安装记录 | `desktop` profile 中 `dsh-greatwall-agent` 为 `link:` 依赖，且已加入 `dsh.profile.bundles` |
| 配置条目 | `Config.listConfigs` 返回 `id: include:greatwall-agent`、`patchId: greatwall-agent`、`status: schema`、`acceptsMissing: true`，默认值 `pythonPath=python`、`cleanroomGate=true` |
| 9 个工具 | `Tool.listTools` 中可见全部 `mcp__greatwall-agent__gw_*` 工具 |
| MCP 桥连通 | `list_mcp_resources(server="greatwall-agent")` 返回 `{"resources":[]}`（该服务只暴露 tools，无 resources，能返回即说明 stdio 桥已连上） |
| MCP 协议 | 手工 stdio 探测 `initialize` 返回 `{"protocolVersion":"2024-11-05","serverInfo":{"name":"greatwall-agent","version":"4.2.0"},"capabilities":{"tools":{}}}`；`tools/list` 返回 9 个工具 |
| 内核逐字节 | `node tools/verify-core.mjs` → `OK: 18 core files match core-manifest.sha256 (byte-identical Antigravity tree)` |
| 端到端测试 | 10 项全过：本轮复跑 `Ran 10 tests in 2.882s / OK`；归档日志 [`docs/audit/e2e_run.log`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/docs/audit/e2e_run.log) 记录 `2.990s` |
| 门禁实拦 | 读 `.kernel_vault`、`shared_readonly` 终端重定向、`../slot_*`、单条命令引用两个槽位均被拒（拒绝文案见下文）；普通命令放行 |
| 环境 | DSH `0.2.2-rc.1`、Node `24.20.0`、Python `3.14.7`（安装验证记录；本机 node/python 复测同版本） |

门禁实测返回的四条固定文案（与 `greatwall-agent/bin/hook_gate.py` 逐字节一致）：

```text
🔒 [长城 Agent 清洁室隔离门禁] 严禁直接读取或修改 `.kernel_vault` 内核保险箱（含评测真值与 HMAC 密钥）！请使用 `gw_*` 标准 MCP 工具交互。
🔒 [长城 Agent 只读档案馆门禁] 严禁通过终端命令重定向或修改 `shared_readonly/` 公共只读区！
🔒 [长城 Agent 只读档案馆门禁] `shared_readonly/` 为公共只读挂载区，严禁直接用写文件工具篡改！请在孤岛 `legacy_out/` 下提交遗产包并通过 `gw_submit_legacy` 验收入库。
🔒 [长城 Agent 跨孤岛防偷看门禁] 严禁通过 `../slot_*` 越界访问其他并行探索槽位的私有目录！
```

### 9.2 未验证（不要当作已保证）

- **非 Windows 平台**：默认 `python3`、路径牢笼与评测隔离的跨平台行为未实测；Windows Job Object 相关能力不适用于其他平台。
- **DSH 版本边界外**：`<0.2.2-rc.1` 与 `>=0.3.0-0` 会被 `engines` 拒绝，本次未实测这些版本的降级行为。
- **npm 发布与市场托管**：GitHub 仓库、npm 包、GitHub Pages 索引 URL 均未发布；`market/index.json` 的 `publishTimestamp` 仍是占位符，发布流程由发布任务负责。
- **技能在会话中的可见性**：安装验证记录确认 `greatwall-campaign` 可用；本文档会话无法从工具侧枚举技能目录，未重复验证。
- **其他 Python 版本 / 虚拟环境**：仅 Python `3.14.7` 实测。

---

## 十、已知限制（刻意未迁移）

1. **`rules/AGENTS.md` 不会自动加载。** DSH 没有 Antigravity 的插件级常驻规则注入点；请按原说明把它复制到攻关工作区（或合入全局规则）。
2. **`agents/*.md` 不会自动注册。** DSH 没有 Antigravity 那种“命名子智能体注册表”；三份提示词原样随包，可手工作为子智能体/子会话的提示词素材。
3. **技能正文是原文。** 除前置一段工具名映射注记外不做改写，因此正文里“8 个原生工具”的旧表述与 `gw_lineage_control` 未覆盖的问题一并保留。
4. **`mcp_config.json` 原样随包但不被读取。** 该文件里是原机器的绝对路径（`C:\Users\wangy\...`），仅作为原插件树的一部分存在；DSH 侧由 `lib/index.js` 动态解析路径。
5. **门禁只能“拒绝”，不能“放行/改写”。** `ctx.tools.guard` 在 pre-execute 策略与审批之后运行，是单调拒绝；它不替代 DSH 自身的审批与沙箱。
6. **硬依赖 `tools` 服务。** 插件 `inject = ['tools']`；没有工具注册表的宿主不会激活本插件（MCP 与技能也一并不激活）。
7. **单次 MCP 调用上限 600 秒。** `toolCallTimeoutMs: 600000` 是为 `gw_evaluate_slot` 这类真实长评测放宽的；更长的任务需在工具内部分段。

---

## 十一、目录结构

```text
dsh-greatwall-agent/
├── package.json                  # npm 包清单：engines、dsh.bundle、peerDependencies、files、scripts（prepack/verify:core/manifest:core）
├── cordis.patch.yml              # bundle 层：一行 insert（id: greatwall-agent）
├── lib/
│   ├── index.js                  # 宿主入口：挂 MCP、注册技能、安装门禁
│   ├── gate.js                   # 清洁室门禁（hook_gate.py 的规则移植 + 宿主字段适配）
│   └── skillpack.js              # 读取/校验 SKILL.md 并注册到 ctx.skills
├── locale/{zh,en}.json           # 插件市场/设置页的标题与描述
├── icon.svg                      # 插件图标
├── tools/
│   ├── clean-pycache.mjs         # prepack：清理 __pycache__/*.pyc，避免缓存进 tarball
│   ├── make-core-manifest.mjs    # 生成 core-manifest.sha256
│   └── verify-core.mjs           # 校验 greatwall-agent/ 与清单逐字节一致
├── core-manifest.sha256          # 18 个内核文件的 SHA-256
├── greatwall-agent/              # 原 Antigravity 插件树（逐字节副本，18 文件）
│   ├── bin/{gw_mcp_server.py,hook_gate.py}
│   ├── lib/{sandbox,archive,evaluator,engine}.py
│   ├── skills/greatwall-campaign/SKILL.md
│   ├── rules/AGENTS.md
│   ├── agents/{gw-distiller,gw-explorer,gw-auditor}.md
│   ├── tests/test_plugin_e2e.py
│   └── plugin.json / mcp_config.json / hooks.json / README.md / assets/logo.svg
├── market/index.json             # DSH 插件市场索引（format 1，发布前含时间戳占位符）
├── .release/verify-index.mjs     # 市场索引离线校验脚本
├── docs/{INSTALL,ARCHITECTURE}.md
└── docs/BUG_REPORT.md            # 原 Python 内核的统一缺陷报告（本轮生成，见第十三节）
```

---

## 十二、校验与测试（维护者）

```powershell
# 0) 进入设计仓库根目录
Set-Location 'D:\Documents\deepseek harness\长城Agent_框架设计'

# 1) 内核逐字节校验：应输出 OK: 18 core files match ...
node 'plugins\dsh-greatwall-agent\tools\verify-core.mjs'

# 2) 10 项端到端验收（零第三方依赖，约 3 秒）
$env:PYTHONUTF8 = '1'
python -W default 'plugins\dsh-greatwall-agent\greatwall-agent\tests\test_plugin_e2e.py'

# 3) 市场索引离线校验（占位符阶段会给出 warning；发布构建用 --strict）
node 'plugins\dsh-greatwall-agent\.release\verify-index.mjs'
```

包内也提供 npm script：`npm run verify:core`、`npm run manifest:core`（在包目录执行）。`npm pack` / `npm publish` 会先执行 `prepack` → `node tools/clean-pycache.mjs`，清掉 `greatwall-agent/` 下的 `__pycache__` 与 `*.pyc`；MCP 子进程还设置了 `PYTHONDONTWRITEBYTECODE=1`，避免在安装目录里重新生成缓存。

---

## 十三、文档与缺陷

- 安装、验证、排障与卸载：[`docs/INSTALL.md`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/docs/INSTALL.md)
- 文件级移植架构与适配细节：[`docs/ARCHITECTURE.md`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/docs/ARCHITECTURE.md)
- English README：[`README.en.md`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/README.en.md)
- 原 Python 内核统一缺陷报告：[`docs/BUG_REPORT.md`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/docs/BUG_REPORT.md)（见 BUG_REPORT.md（本轮生成））
- 设计仓库归档档案（物理位置、发布与维护命令）：`17_长城Agent_V4-DSH插件移植档案.md`（设计仓库根目录）

> 本插件坚持“报告而不修复”内核缺陷：`greatwall-agent/` 与 `core-manifest.sha256` 一旦改动，`verify-core.mjs` 立即失败。任何内核问题请写进 [`docs/BUG_REPORT.md`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/docs/BUG_REPORT.md)，不要就地改 `greatwall-agent/`。

---

## 十四、许可证

MIT，见 [`LICENSE`](https://github.com/Qingzhu093/dsh-greatwall-agent/blob/main/LICENSE)。原 `greatwall-agent` 插件同样以 MIT 随包分发，版权归 Great Wall Agent Contributors。
