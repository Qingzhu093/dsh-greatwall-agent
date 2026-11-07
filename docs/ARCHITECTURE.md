# 架构与移植说明 — `dsh-greatwall-agent`

> 本文回答三个问题：**原插件的每个文件去了哪里**、**三项宿主能力是怎么重写的**、**哪些东西刻意没有改**。
> 安装与验证步骤见 [`INSTALL.md`](INSTALL.md)；用户视角见 [`../README.md`](../README.md)。
> 文中“实测”指 2026-11-07 在本机 `desktop` profile（DSH `0.2.2-rc.1`）的观察结果。

---

## 一、设计原则：内核与宿主壳解耦

原 Antigravity 插件本身就分成两层；本包沿用这条分界线，只替换宿主层：

| 层 | 原插件内容 | 本包处理 |
| :--- | :--- | :--- |
| 跨平台内核 | `lib/{sandbox,archive,evaluator,engine}.py`、`bin/gw_mcp_server.py`、`bin/hook_gate.py`、`tests/test_plugin_e2e.py` | **逐字节复制**到 `greatwall-agent/`，被 `core-manifest.sha256` 固定 |
| 宿主薄壳 | `plugin.json`、`mcp_config.json`、`hooks.json`、`skills/`、`rules/`、`agents/` | 用 DSH 原生扩展点重写（MCP 挂载 / 技能注册 / 工具守卫）；无法对应的两项原样随包 |

“逐字节”不是文档措辞，而是可执行断言：

```powershell
Set-Location 'D:\Documents\deepseek harness\长城Agent_框架设计'
node 'plugins\dsh-greatwall-agent\tools\verify-core.mjs'
# OK: 18 core files match core-manifest.sha256 (byte-identical Antigravity tree)
```

`tools/make-core-manifest.mjs` 生成清单；`tools/verify-core.mjs` 逐文件比对，并检查“清单外多余文件”。`__pycache__/`、`*.pyc`、`.pytest_cache/`、`node_modules/` 被明确排除。

---

## 二、文件级移植映射

### 2.1 原插件文件 → 本包处理

| 原文件（`plugins/greatwall-agent/`） | 原职责 | 本包处理 | 落点 |
| :--- | :--- | :--- | :--- |
| `bin/gw_mcp_server.py` | JSON-RPC 2.0 stdio MCP 服务，暴露 9 个 `gw_*` 工具 | 原样随包；由 DSH 官方 MCP 客户端以子进程拉起 | `greatwall-agent/bin/gw_mcp_server.py` |
| `lib/{sandbox,archive,evaluator,engine}.py`、`lib/__init__.py` | 沙箱、档案、评测、状态机内核 | 原样随包，运行时被 MCP 服务 import | `greatwall-agent/lib/` |
| `bin/hook_gate.py` | Antigravity `PreToolUse` 门禁：stdin JSON → `{"decision":"deny","reason":...}` | **规则移植**为 DSH 工具守卫（见第四节）；原脚本仍随包（内含 `evaluate_hook` 作为对照物） | `lib/gate.js` + `greatwall-agent/bin/hook_gate.py` |
| `hooks.json` | `PreToolUse` 挂载声明（matcher + command 绝对路径） | 不加载；改由 `apply()` 里 `ctx.tools.guard()` 注册 | `lib/index.js` |
| `mcp_config.json` | stdio 服务注册（`python.exe` 与脚本绝对路径） | 不加载；改由 `apply()` 里 `ctx.plugin(McpClient, ...)` 挂载，路径从 `import.meta.url` 解析 | `lib/index.js` |
| `plugin.json` | Antigravity 插件元数据（名称、版本、logo、suggestedPrompts） | 不可直接复用；对应信息拆到 `package.json`（`dsh.bundle`、`icon`）+ `locale/{zh,en}.json`（标题/描述） | `package.json`、`locale/` |
| `assets/logo.svg` | 插件图标 | 复制为包图标 `icon.svg`；市场索引再复制一份到 `market/icons/`。三者 SHA-256 相同（`25942ae8…`） | `icon.svg` |
| `skills/greatwall-campaign/SKILL.md` | 四阶段作业手册 | **运行时注册**：正文逐字，仅前置一段工具名映射注记 | `lib/skillpack.js`、`lib/index.js` |
| `rules/AGENTS.md` | 常驻攻关铁律 | **不自动装载**；原样随包，按原说明复制到工作区/全局规则 | `greatwall-agent/rules/AGENTS.md` |
| `agents/{gw-distiller,gw-explorer,gw-auditor}.md` | Antigravity 命名子智能体清单与系统提示词 | **不自动注册**；原样随包，作为提示词素材 | `greatwall-agent/agents/` |
| `tests/test_plugin_e2e.py` | 10 项端到端/对抗验收 | 原样随包；可直接运行 | `greatwall-agent/tests/test_plugin_e2e.py` |
| `README.md` | Antigravity 版说明 | 原样随包（位于 `greatwall-agent/README.md`）；**包根部的 `README.md` 是本 DSH 版新写的** | `greatwall-agent/README.md` |

### 2.2 本包新增的宿主文件

| 文件 | 职责 |
| :--- | :--- |
| `package.json` | npm 清单：`engines.dsh`/`engines.node`、`dsh.bundle.patch`、`peerDependencies`、`files`、`icon`、`scripts`（`prepack`/`verify:core`/`manifest:core`） |
| `cordis.patch.yml` | bundle 层：**一行** `insert`（`id: greatwall-agent`，`name: dsh-greatwall-agent`），故意不写 `config` |
| `lib/index.js` | 宿主入口：`name`/`inject`/`Config`/`apply`；挂 MCP、注册技能、安装门禁 |
| `lib/gate.js` | `hook_gate.py` 的三条规则 + 宿主字段适配；导出规则常量与 `evaluateGate` |
| `lib/skillpack.js` | 发现/解析/校验 `SKILL.md`，注册到 `ctx.skills`（不 import 任何 DSH 包，便于 `node --test` 单测） |
| `locale/{zh,en}.json` | 市场/设置页展示用的标题与描述（`meta.title`/`meta.description`） |
| `tools/make-core-manifest.mjs`、`tools/verify-core.mjs`、`tools/clean-pycache.mjs` | 生成/校验 `core-manifest.sha256`；`prepack` 时清理 Python 字节码缓存 |
| `core-manifest.sha256` | 18 个内核文件 SHA-256 |
| `market/index.json`、`market/icons/` | DSH 插件市场索引（`format: 1`） |
| `.release/verify-index.mjs` | 市场索引离线校验（`--strict` 用于发布构建） |
| `docs/INSTALL.md`、`docs/ARCHITECTURE.md` | 本文档族 |

---

## 三、MCP 桥：为什么在 JS 里挂载，而不是写进 `cordis.patch.yml`

DSH 的 `cordis.patch.yml` 里完全可以写两行：一行挂本插件，一行挂 `@deepseek-ai/dsh-mcp-client` 并给它 `command`/`args`。本包没有这么做，原因只有一个——**脚本路径**。

`lib/index.js` 的注释把理由写得很直白：

```js
// The MCP server is mounted from JavaScript rather than declared in
// `cordis.patch.yml` for one reason: the patch row would need an absolute path to
// `greatwall-agent/bin/gw_mcp_server.py`, while a JS mount resolves it from
// `import.meta.url`. The same package therefore works from a profile install, a
// pnpm store, a linked checkout, or `node_modules`, on every platform.
```

补丁文件是静态 YAML：写死 `D:\...\bin\gw_mcp_server.py` 就只能在作者那台机器、那个安装方式下工作；写相对路径则相对的是 profile 目录而不是包目录。JS 挂载可以在运行时算路径：

```js
const CORE_ROOT = fileURLToPath(new URL('../greatwall-agent/', import.meta.url))
const SERVER_SCRIPT = fileURLToPath(new URL('../greatwall-agent/bin/gw_mcp_server.py', import.meta.url))
const SKILLS_DIR = fileURLToPath(new URL('../greatwall-agent/skills/', import.meta.url))
```

于是同一份包在 `link:` 安装、`node_modules` 安装、pnpm store、tarball 解包后都能定位到内核与技能。

### 3.1 挂载参数（`mountMcpServer`）

| 参数 | 值 | 说明 |
| :--- | :--- | :--- |
| `transport` | `stdio` | 与原 `mcp_config.json` 相同 |
| `serverName` | `greatwall-agent` | 与原 MCP 键一致；决定模型侧前缀 `mcp__greatwall-agent__` |
| `command` | `pythonPath` | 默认 Windows `python`、其他平台 `python3`，可配置 |
| `args` | `[SERVER_SCRIPT]` | 运行时解析出的绝对路径 |
| `env.PYTHONUTF8` | `1` | 与原配置一致 |
| `env.PYTHONIOENCODING` | `utf-8` | 保证 stdout 为 UTF-8 |
| `env.PYTHONUNBUFFERED` | `1` | 避免管道缓冲拖慢 JSON-RPC 响应 |
| `env.PYTHONDONTWRITEBYTECODE` | `1` | 不在安装目录写 `__pycache__`：`files` 白名单优先于 `.gitignore`，运行期缓存会被打进 tarball，`prepack` 另有一道清理 |
| `toolCallTimeoutMs` | `600000` | 为 `gw_evaluate_slot` 等真实长评测放宽（默认 60 秒） |
| `failOnStartupError` | `false` | Python 缺失时插件降级为“无工具”，不拖垮整个 profile |
| `reconnect` | `{ enabled: true, initialDelayMs: 500, maxDelayMs: 30000, maxAttempts: 10 }` | 子进程意外退出时有限重连 |

`ctx.plugin(McpClient, {...})` 把 MCP 客户端挂在本插件的上下文中：子进程生命周期跟随插件；插件卸载时一并回收。

### 3.2 模型侧工具名

`serverName` 决定前缀。`lib/index.js` 的注释记录了命名约束：命名空间必须匹配 `^[A-Za-z0-9_-]{1,32}$`，`greatwall-agent` 满足。实测 `Tool.listTools` 中 9 个工具名为：

```text
mcp__greatwall-agent__gw_init_campaign
mcp__greatwall-agent__gw_lock_distillation
mcp__greatwall-agent__gw_allocate_slot
mcp__greatwall-agent__gw_surgical_replace
mcp__greatwall-agent__gw_evaluate_slot
mcp__greatwall-agent__gw_submit_legacy
mcp__greatwall-agent__gw_lineage_control
mcp__greatwall-agent__gw_archive_query
mcp__greatwall-agent__gw_compile_delivery
```

> 工具参数与返回完全由 `gw_mcp_server.py` 决定，本包没有包装、改名或改写任何 `inputSchema`。

---

## 四、清洁室门禁的适配

### 4.1 两代宿主契约的差异

| 维度 | Antigravity（原实现） | DSH（本包） |
| :--- | :--- | :--- |
| 挂载方式 | `hooks.json` 的 `PreToolUse` matcher | `ctx.tools.guard(callback)` |
| 输入 | stdin 一段 `{"toolCall":{"name","args":{...}}}` | `ToolExecution`（`name`、`arguments` 等） |
| 输出 | stdout `{"decision":"deny","reason":...}` / `{"decision":"allow"}` | 返回 `string`（拒绝原因）或 `undefined`（放行） |
| 时序 | 由 Antigravity 钩子管线调用 | 在 pre-execute 策略与审批**之后**运行，只能单调拒绝 |
| 调用形态 | 独立 Python 进程，每次调用 fork | 同进程 JS 回调，快路径约 0.1 ms（无标记时直接返回） |

DSH 侧契约来自运行时 `Service` 检查（`tools` 服务）：`guard(guard: ToolGuard): () => void`，`ToolGuard = (execution) => string | undefined`，描述为 “Register a monotonic denial in the calling scope”，并在 `checkGuards` 中 “after pre-execute policy and approval resolve”。因此**门禁不能替代审批/沙箱，只能追加拒绝**。

### 4.2 字段适配表（`PATH_FIELDS` / `COMMAND_FIELDS`）

Antigravity 只认 `Path`/`TargetFile`/`CommandLine`；DSH 的工具参数名不同，所以 `gate.js` 同时接受两套拼写：

| 语义 | Antigravity 字段 | DSH 侧优先字段（`gate.js` 全量接受） |
| :--- | :--- | :--- |
| 路径 | `Path`、`TargetFile` | `file_path`、`path`、`target_path`、`targetPath`、`target_file`、`targetFile`、`target`、`source_path`、`destination_path`、`cwd`、`directory`、`dir`，以及 `Path`、`TargetFile` |
| 命令行 | `CommandLine` | `command`、`cmd`、`script`、`CommandLine`、`text` |

工具名同样是两套并存：

| 类别 | Antigravity 名单 | DSH 侧新增（`WRITE_TOOLS` / `COMMAND_TOOLS`） |
| :--- | :--- | :--- |
| 写文件工具 | `write_file`、`edit_file`、`replace_file_content`、`multi_replace_file_content` | `write`、`edit`、`multi_edit`、`multiedit`、`apply_patch` |
| 执行命令工具 | `run_command` | `pwsh`、`bash`、`shell`、`execute_command`、`terminal_send` |

匹配前统一做 `\` → `/` 归一化（与 `hook_gate.py` 的 `replace("\\", "/")` 相同）；工具名在 JS 侧转小写后比较。

### 4.3 三条规则（顺序与策略与原脚本一致）

```text
快速放行：路径文本 + 命令文本中若不含下列任一标记 → 直接 allow
          .kernel_vault | shared_readonly | worktrees/slot_ | ../slot_

规则 1：出现 .kernel_vault → deny（任何工具，读写命令一律拒绝）
规则 2：出现 shared_readonly →
          a) 工具属于写文件集合 → deny（文件写入）
          b) 工具属于命令集合 且 命令命中重定向/写入模式 → deny（终端写入）
规则 3：出现 ../slot_ → deny（跨槽位越界）
        单次调用中出现 ≥2 个不同的 worktrees/slot_* → deny（跨槽位偷看）
```

终端写入模式与原脚本同序：`>`、`Out-File`、`Set-Content`、`Add-Content`、`Remove-Item`、`rm `、`del `、`mv `、`Move-Item`（大小写不敏感）。

### 4.4 拒绝文案与已知差异

四条**固定**拒绝文案与 `hook_gate.py` 逐字节一致（`.kernel_vault`、`shared_readonly` 文件写入、`shared_readonly` 终端写入、`../slot_*`），见 [`../README.md`](../README.md) 第 9.1 节。

第五条是**动态**文案（单次操作引用多个槽位）。两者语义相同，但槽位列表的序列化格式不同：

| | 输出示例 |
| :--- | :--- |
| `hook_gate.py`（Python `repr`） | `['slot_01_node-a', 'slot_02_node-b']`（单引号 + 逗号后空格） |
| `gate.js`（`JSON.stringify`） | `["slot_01_node-a","slot_02_node-b"]`（双引号、无空格） |

实测 DSH 侧：

```text
🔒 [长城 Agent 跨孤岛防偷看门禁] 检测到单次操作同时引用多个孤岛槽位 ["slot_01_node-a","slot_02_node-b"]，严禁跨槽位偷看或拷贝未验收入库的半成品代码！
```

因此准确表述是：**四条固定文案逐字节一致，动态多槽位文案仅语义一致**。其余实现层差异：

- Python 只在 `cmd_line` 上做写入模式匹配；JS 在归一化后的 `commandText` 上匹配（归一化不改变这些模式的含义）。
- Python 工具名精确比较；JS 先转小写（Antigravity 工具名本身都是小写，无行为差异）。
- JS 会把多个字段的值用空格拼起来整体匹配（覆盖更广，例如同时出现在 `file_path` 与 `command` 的标记都能命中）。
- 覆盖的工具名集合更大（DSH 的 `write`/`edit`/`pwsh`/`terminal_send` 等必须纳入，否则同样的规则在 DSH 上拦不住）。

### 4.5 挂载方式与降级

```js
export const inject = ['tools']

function installCleanroomGate(ctx, enabled) {
  if (!enabled) return false
  const registry = ctx.tools
  if (!registry || typeof registry.guard !== 'function') return false
  ctx.effect(
    () => registry.guard((execution) => evaluateGate(execution?.name, execution?.arguments)),
    'dsh-greatwall-agent.cleanroomGate',
  )
  return true
}
```

- `inject = ['tools']`：本插件硬依赖工具注册表；没有 `tools` 服务的宿主不会激活插件。
- `ctx.effect(...)` 绑定生命周期：插件卸载时守卫自动撤销。
- `cleanroomGate: false` 时**完全不注册**守卫，不是宽松模式。

---

## 五、技能交付机制

### 5.1 为什么不能靠“把 skills/ 目录放进包里”

DSH 的技能提供方只从**配置的根目录**发现技能（项目 `.dsh/skills`、`$DSH_HOME/skills`、`Config.customSkillDirs`、`Config.bundledSkillDir`）。npm 包自己的 `skills/` 不在其中，所以 npm 交付的插件必须自己注册——这正是 `lib/skillpack.js` 头部注释记录的设计约束，也是本包选择 `ctx.skills.register()` 而非安装脚本、符号链接或改 profile 的原因。

### 5.2 流水线

```text
greatwall-agent/skills/greatwall-campaign/SKILL.md
        │  fs.readdirSync + 每子目录一个 SKILL.md
        ▼
loadSkillPack()  →  parseSkillDocument()（极简 frontmatter：name / description / whenToUse）
        │  校验：kebab-case 名称、名称与目录一致、正文非空；问题进 problems 而不是静默丢弃
        ▼
registerSkillPack(service, skills, { provider: 'dsh-greatwall-agent' })
        │  service.register({ name, description, whenToUse?, content, invocation, provider })
        ▼
ctx.skills（运行时技能层）
```

- **正文**：`parseSkillDocument` 去掉 frontmatter，取剩余正文；`lib/index.js` 只对 `greatwall-campaign` 前置 `HOST_MAPPING_NOTE`（工具名映射说明），其余技能不加工。
- **调用策略**：`modelInvocable: true`、`userInvocable: true`（默认）。
- **生命周期**：`register()` 返回 Cordis effect disposer，插件卸载时技能自动消失。
- **失败隔离**：单个技能解析/注册失败只记入 `failed`/`problems` 并 `logger.warn`，不会中断插件其余能力。
- **服务契约**：运行时 `skills` 服务确认为 `register(skill: SkillRegistration)`，描述为“把 borrowed readonly runtime skill 注册进调用上下文的层”；同层同名运行时技能 first-wins。实测 0.2.2-rc.1 上 `greatwall-campaign` 注册成功。

> 注意：注册的是**运行时**技能（`source` 不是 project/user 目录），不会在磁盘上产生技能文件，也不会修改 profile。

---

## 六、配置与加载契约

### 6.1 Schemastery `Config`

```js
export const Config = Schema.object({
  pythonPath: Schema.string().default(DEFAULT_PYTHON),
  cleanroomGate: Schema.boolean().default(true),
})
```

- `DEFAULT_PYTHON = process.platform === 'win32' ? 'python' : 'python3'`。
- `cordis.patch.yml` **不写 `config`**：Cordis 在 `apply` 前用 schema 校验并填默认值，默认值只应存在于一处；补丁里的 `config` 会整体替换而非深合并，重复默认值会在用户只覆盖一个字段时把另一个字段丢掉（`cordis.patch.yml` 注释记录了这一点）。
- 运行时 Config 检查确认：条目 `include:greatwall-agent`，`status: schema`，`acceptsMissing: true`，默认 `pythonPath=python`、`cleanroomGate=true`（Windows 上）。
- `apply()` 还会对 `pythonPath` 做一次防御性 trim：空字符串回落到平台默认值。

### 6.2 `apply()` 与错误隔离

`apply(ctx, config)` 是同步函数，按顺序交付三个能力，每个独立兜底：

| 子系统 | 失败时的行为 | 代码保障 |
| :--- | :--- | :--- |
| MCP 挂载 | 记录 warn，插件继续（技能/门禁仍可用） | `mountMcpServer` 内 try/catch；`failOnStartupError: false` |
| 技能注册 | 记录 warn，技能缺失 | `deliverSkillPack` 内 try/catch + `problems`/`failed` 列表 |
| 清洁室门禁 | 返回 `false`，不注册 | 检查 `ctx.tools.guard` 是否存在；`cleanroomGate` 开关 |

`apply()` 返回 `{ mcp, skills, gate }` 供宿主/测试观察；并输出一行 info 日志：

```text
[dsh-greatwall-agent] core=<package>/greatwall-agent/ python=python mcp=greatwall-agent skills=greatwall-campaign gate=on
```

日志通过 `safeLogger` 读取 `ctx.logger ?? ctx.root.logger`，任何 logger 异常都被吞掉——日志失败不得影响激活。

---

## 七、“未改动”清单（逐字节随包）

`greatwall-agent/` 下 18 个文件全部原样，SHA-256 记录在 `core-manifest.sha256`：

| 文件 | 字节数 | 角色 |
| :--- | ---: | :--- |
| `README.md` | 4498 | Antigravity 版说明 |
| `plugin.json` | 962 | Antigravity 清单（含 `suggestedPrompts`） |
| `mcp_config.json` | 355 | Antigravity stdio 配置（**含绝对路径，DSH 不读取**） |
| `hooks.json` | 456 | PreToolUse 钩子声明（**DSH 不读取**） |
| `assets/logo.svg` | 1675 | 图标（与 `icon.svg`、市场图标同哈希） |
| `bin/gw_mcp_server.py` | 28979 | 9 工具 stdio MCP 服务 |
| `bin/hook_gate.py` | 4519 | PreToolUse 门禁脚本（规则对照物） |
| `lib/__init__.py` | 1306 | 包导出 |
| `lib/sandbox.py` | 34984 | 路径牢笼、Job Object、文件锁、AST 微创替换 |
| `lib/archive.py` | 44204 | L0/L1/L2 档案馆、原语提取、撤回树 |
| `lib/evaluator.py` | 43820 | AST 审计、HMAC 评测、差分互测、勘误 |
| `lib/engine.py` | 55373 | 状态机、EDA 探针、60 步锁、终局编译 |
| `rules/AGENTS.md` | 3470 | 常驻攻关铁律 |
| `skills/greatwall-campaign/SKILL.md` | 7147 | 四阶段作业手册 |
| `agents/gw-distiller.md` | 1909 | Phase 0 蒸馏提示词 |
| `agents/gw-explorer.md` | 2349 | 清洁室探索提示词 |
| `agents/gw-auditor.md` | 1842 | 独立审计/内省室提示词 |
| `tests/test_plugin_e2e.py` | 33991 | 10 项端到端验收 |

明确**未改动**的行为：9 个工具的名称、`inputSchema`、默认值、返回值、裁决阈值；`evaluate_hook` 的三条规则与四条固定拒绝文案；技能正文（除前置映射注记）。任何对内核的“顺手优化”都会让 `verify-core.mjs` 失败——内核问题请写进 [`BUG_REPORT.md`](BUG_REPORT.md)，不要直接改 `greatwall-agent/`。

打包相关：`package.json` 的 `files` 白名单包含整个 `greatwall-agent/` 目录，而 `files` 白名单优先于 `.gitignore`，所以运行期产生的 `__pycache__/*.pyc` **可能**被打进 tarball。为此有两道防线：`prepack` 自动执行 `node tools/clean-pycache.mjs` 清理缓存，MCP 子进程设置 `PYTHONDONTWRITEBYTECODE=1` 从源头避免在安装目录内生成缓存。`files` 同时包含 `tools` 与 `core-manifest.sha256`，因此安装后的包也能自证内核未变。

---

## 八、边界与未验证项

- **非 Windows**：路径牢笼与评测的跨平台行为、`python3` 默认解释器均未实测；`test_09` 的 Windows Job Object 能力在其他平台不适用。
- **其他 DSH 版本**：`engines.dsh` 之外会被拒绝，降级行为未测。
- **技能正文中的“8 个原生工具”**：原 `SKILL.md` 的既有表述，覆盖 8 个工具；实际 MCP 暴露 9 个（`gw_lineage_control` 只在工具描述中）。本包按“逐字节不改”保留。
- **门禁不是安全边界**：它只能在调用发起后拒绝，无法阻止绕过 DSH 工具管线直接运行的程序；真正的隔离仍由 DSH 沙箱/审批与内核的 `SandboxPathJail` 负责。
- **市场索引**：`market/index.json` 仍是发布前状态（`publishTimestamp` 占位符），托管 URL 未启用。
