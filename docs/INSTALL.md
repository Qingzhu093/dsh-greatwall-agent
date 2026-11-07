# 安装、验证与排障 — `dsh-greatwall-agent`

> 适用于 `dsh-greatwall-agent@4.2.0`（`engines.dsh: >=0.2.2-rc.1 <0.3.0-0`）。
> 本文所有命令均在 **PowerShell 7** 下可执行；设计仓库根目录为 `D:\Documents\deepseek harness\长城Agent_框架设计`。
> 首次阅读建议先看 [`README.md`](../README.md) 的“宿主能力映射”与“已知限制”两节。

---

## 一、前置检查

```powershell
Set-Location 'D:\Documents\deepseek harness\长城Agent_框架设计'
node --version      # 需要 ^22.19.0 || >=24.0.0
python --version    # 需要可用的 Python 3（本机 3.14.7）
dsh --version       # 需要满足 engines.dsh 的 DSH
```

| 检查项 | 要求 | 本机实测（2026-11-07） |
| :--- | :--- | :--- |
| Node.js | `^22.19.0 \|\| >=24.0.0` | `v24.20.0` ✅ |
| Python | 3.x，仅标准库 | `Python 3.14.7` ✅ |
| DSH（运行插件的那个安装） | `>=0.2.2-rc.1 <0.3.0-0` | DSH Desktop `0.2.2-rc.1` ✅ |
| 独立 `dsh` CLI | 同上 | `0.1.5-rc.1` ❌（太旧，且无法管理 Electron profile） |
| pnpm（仅 CLI 安装需要） | 在 `PATH` 中 | 未安装（CLI 安装会失败） |

> **重要区分**：运行插件的 DSH 与 PATH 上的独立 `dsh` CLI 可能是两个不同安装。本机 Desktop 内的 DSH 是 `0.2.2-rc.1`；`C:\Users\wangy\nodejs\dsh.ps1` 自报 `0.1.5-rc.1`。用 CLI 安装前，先确认 CLI 版本满足 `engines.dsh`。

---

## 二、安装

### 2.1 DSH Desktop（Electron 托管 profile，本机已验证）

DSH Desktop 的 `desktop` profile 由 Electron 应用独占管理，**只能用应用内插件管理入口安装**。安装后 profile 清单会写入：

```json
"dependencies": {
  "dsh-greatwall-agent": "link:D:/Documents/deepseek harness/长城Agent_框架设计/plugins/dsh-greatwall-agent"
}
```

并把 `dsh-greatwall-agent` 追加到 `C:\Users\wangy\.dsh\profiles\desktop\package.json` 的 `dsh.profile.bundles` 数组。

若误用 CLI：

```powershell
dsh plugin --profile desktop add dsh-greatwall-agent
# error: profile "desktop" is managed exclusively by the Electron application
```

`dsh --profile desktop --dump-config` 同样会被拒绝（实测）。Electron profile 的验证请走[第三节](#三安装后验证)的 inspect 方式。

### 2.2 CLI 托管 profile：从 npm 安装（发布后可用）

```powershell
dsh plugin --profile <profile-name> add dsh-greatwall-agent
```

- 首次使用会初始化该 profile；`dsh plugin` 把参数**转发给 pnpm**，所以 `PATH` 中必须有 pnpm。本机实测缺 pnpm 时输出：

```text
'pnpm' is not recognized as an internal or external command,
operable program or batch file.
dsh: pnpm failed in profile directory C:\Users\wangy\.dsh\profiles\<profile-name>
```

- 安装完成后查看组合层：`dsh --profile <profile-name> --dump-config`（应出现本包的一层与 `greatwall-agent` 行）。

### 2.3 CLI 托管 profile：从本地目录安装（link）

```powershell
dsh plugin --profile <profile-name> add 'D:\Documents\deepseek harness\长城Agent_框架设计\plugins\dsh-greatwall-agent'
```

路径含空格，PowerShell 7 中必须加单引号。link 安装会直接指向工作区目录，后续改 `lib/` 或 `greatwall-agent/` 无需重装（重启 DSH 会话生效）。

### 2.4 从 tarball 安装

```powershell
Set-Location 'plugins\dsh-greatwall-agent'
npm pack
# 生成 dsh-greatwall-agent-4.2.0.tgz
dsh plugin --profile <profile-name> add '.\dsh-greatwall-agent-4.2.0.tgz'
```

`package.json` 的 `files` 白名单包含 `lib`、`locale`、`tools`、`cordis.patch.yml`、`icon.svg`、`core-manifest.sha256`、`README.md`、`README.en.md`、`LICENSE`、`greatwall-agent`，tarball 内应能看到这些内容。`npm pack` 会先触发 `prepack` → `node tools/clean-pycache.mjs`，自动移除 `greatwall-agent/` 下的 `__pycache__`/`*.pyc`：`files` 白名单优先于 `.gitignore`，必须靠这一步兜底。

### 2.5 从插件市场索引安装（发布后）

源码目录中的索引文件：[`../market/index.json`](../market/index.json)（`format: 1`，图标在 `../market/icons/`）。注意 `market/` 不在 npm tarball 的 `files` 白名单内，市场索引由仓库静态托管，不随 npm 包分发。

发布前必须完成的替换：

```text
"publishTimestamp": "__PUBLISH_TIMESTAMP__"   ← 换成真实 Unix 秒
```

校验脚本：

```powershell
Set-Location 'plugins\dsh-greatwall-agent'
node .release\verify-index.mjs            # 占位符阶段：通过但给 warning
node .release\verify-index.mjs --strict   # 发布构建：占位符直接失败
```

托管后，在 DSH 中：**Plugins → Experimental plugins 旁的 More → 打开 Custom plugin markets → Discover → Add index source**，填入索引 URL，再在卡片上安装。计划地址（本轮未发布、未验证）：

```text
https://qingzhu093.github.io/dsh-greatwall-agent/market/index.json
```

---

## 三、安装后验证

按顺序执行；每一步都给出**预期结果**。前四步在 DSH 会话里让 Agent 调用 inspect 工具即可（不需要 shell）。

### 3.1 配置行是否挂上

调用：

```text
cordis_inspect_query(
  platform: "host",
  provider: "Config",
  method: "listConfigs",
  input: { "name": "dsh-greatwall-agent" }
)
```

预期（本机 `desktop` profile 实测）：

```json
{
  "entries": [
    {
      "id": "include:greatwall-agent",
      "patchId": "greatwall-agent",
      "name": "dsh-greatwall-agent",
      "status": "schema"
    }
  ],
  "total": 1,
  "nextOffset": null
}
```

再取该条目的完整 schema：

```text
cordis_inspect_query(
  platform: "host",
  provider: "Config",
  method: "listConfigs",
  input: { "entry": "include:greatwall-agent" }
)
```

预期能看到 `"acceptsMissing": true`、`"packageDir": "...\\node_modules\\dsh-greatwall-agent"`，以及两个字段的默认值：

```json
"pythonPath": { "default": "python", ... },
"cleanroomGate": { "default": true, ... }
```

### 3.2 9 个 MCP 工具是否可见

调用 `cordis_inspect_query(platform: "host", provider: "Tool", method: "listTools")`，在结果中确认以下 9 个名字全部存在：

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

`listTools` 的输出很大会被截断，按前缀 `mcp__greatwall-agent__gw_` 过滤即可（本机实测正好 9 条）。

### 3.3 MCP 连接是否健康

调用 `list_mcp_resources(server: "greatwall-agent")`，预期：

```json
{"resources": []}
```

该服务只声明 `tools` 能力、没有 resources，所以**空列表就是成功**；如果 stdio 子进程起不来，这里会报连接/启动错误。

### 3.4 绕过 DSH 直接验证 MCP 协议（可选）

```powershell
Set-Location 'D:\Documents\deepseek harness\长城Agent_框架设计'
'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' |
  python 'plugins\dsh-greatwall-agent\greatwall-agent\bin\gw_mcp_server.py'
```

预期输出一行 JSON：

```json
{"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "greatwall-agent", "version": "4.2.0"}, "capabilities": {"tools": {}}}}
```

再验证工具数：

```powershell
'{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' |
  python 'plugins\dsh-greatwall-agent\greatwall-agent\bin\gw_mcp_server.py' |
  ForEach-Object { ($_ | ConvertFrom-Json).result.tools.Count }
# 预期：9
```

### 3.5 技能是否注册

让 Agent 加载技能 `greatwall-campaign`（`skill` 工具，名称精确匹配）。能加载即说明 `ctx.skills.register()` 成功；若报“未知技能”，见[第四节](#四故障排查)。

也可以看插件激活日志（`safeLogger` 输出的 info 行）：

```text
[dsh-greatwall-agent] core=<...> python=python mcp=greatwall-agent skills=greatwall-campaign gate=on
```

### 3.6 内核逐字节校验

```powershell
Set-Location 'D:\Documents\deepseek harness\长城Agent_框架设计'
node 'plugins\dsh-greatwall-agent\tools\verify-core.mjs'
```

预期（本机实测）：

```text
OK: 18 core files match core-manifest.sha256 (byte-identical Antigravity tree)
```

校验内容：`greatwall-agent/` 下 18 个文件的 SHA-256 与 `core-manifest.sha256` 完全一致，且没有多余文件（`__pycache__`、`*.pyc` 被忽略）。失败说明内核被改动过。

### 3.7 端到端验收（10 项）

```powershell
Set-Location 'D:\Documents\deepseek harness\长城Agent_框架设计'
$env:PYTHONUTF8 = '1'
python -W default 'plugins\dsh-greatwall-agent\greatwall-agent\tests\test_plugin_e2e.py'
```

预期结尾：

```text
----------------------------------------------------------------------
Ran 10 tests in 2.882s

OK
```

耗时约 3 秒；测试全部在临时目录中运行，不写入本仓库。

### 3.8 门禁是否真的在拦（可选，会产生 4 次“工具失败”）

在 DSH 会话中触发以下四类调用，应分别得到对应的 🔒 拒绝文案，而普通命令应正常执行：

| 触发方式 | 预期结果 |
| :--- | :--- |
| 用文件工具读/写路径含 `.kernel_vault` | `🔒 [长城 Agent 清洁室隔离门禁] ...` |
| 用终端命令写路径含 `shared_readonly`（含 `>` 重定向） | `🔒 [长城 Agent 只读档案馆门禁] ...` |
| 访问/引用 `../slot_*` | `🔒 [长城 Agent 跨孤岛防偷看门禁] ...` |
| 一条命令同时出现两个 `worktrees/slot_*` | 同上（带槽位列表） |
| 普通命令（不含四类标记） | 正常执行 |

> 门禁只认四个敏感标记：`.kernel_vault`、`shared_readonly`、`worktrees/slot_`、`../slot_`。路径里不出现这些字符串，就不会被拦。

---

## 四、故障排查

| 现象 | 最可能原因 | 处理 |
| :--- | :--- | :--- |
| 配置行存在，但 9 个工具不出现 | Python 缺失 / `pythonPath` 指向错误 | 先跑 3.4 的手工 MCP 探测；改 `pythonPath`（见 4.1） |
| 工具不出现，日志有 `MCP mount failed` | MCP 客户端挂载异常 | 看 DSH 日志里的异常文本；确认 `@deepseek-ai/dsh-mcp-client` 已安装 |
| MCP 子进程反复重连 | 服务器启动即崩溃 / stdout 污染 | 见 4.2；用 3.4 直接跑服务器看 stderr |
| 门禁误伤正常命令 | 命令/路径里含敏感标记子串 | 改写路径，或临时 `cleanroomGate: false`（见 4.3） |
| 技能不出现 | 宿主没有 skills 服务，或技能解析失败 | 看日志里 `skills=none` 与 `skill pack problems` |
| 安装被拒，提示版本不满足 | DSH 版本不在 `engines.dsh` 范围 | 升级 DSH；不要用 `0.1.5-rc.1` 的 CLI 装 |
| CLI 报 profile 被 Electron 独占 | 对 `desktop` 等应用管理 profile 用了 CLI | 改用应用内插件管理（见 2.1） |
| 控制台中文乱码 | Windows 代码页 | `$env:PYTHONUTF8='1'`；或 `[Console]::OutputEncoding = [Text.UTF8Encoding]::new()` |

### 4.1 指定 Python 解释器（`pythonPath`）

在 profile 自己的 `cordis.patch.yml` 中按 patch id `greatwall-agent` 覆盖整行（注意 `config` 是整体替换）：

```yaml
- id: greatwall-agent
  name: 'dsh-greatwall-agent'
  config:
    pythonPath: 'C:\Users\wangy\AppData\Local\Programs\Python\Python314\python.exe'
    cleanroomGate: true
```

改完重启 DSH 会话（或重载插件）生效。默认值：Windows 用 `python`，其他平台用 `python3`。

### 4.2 MCP 连不上：三种常见原因

1. **Python 不存在或不可执行**：`pythonPath` 指向的解释器无法启动。用 3.4 的命令直接跑服务器即可复现。
2. **`pythonPath` 指错**：例如指向了 `conda`/`py` 启动器或另一个虚拟环境。改成绝对路径的 `python.exe`。
3. **stdout 污染**：MCP stdio 协议要求子进程 stdout 上**只有 JSON-RPC 帧**。任何 `print()`、conda 激活横幅、包装脚本的提示语都会让客户端解析失败。排查方式：

```powershell
# 正常情况：下面只输出一行 JSON；若出现任何非 JSON 行，就是污染源
'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' |
  python 'plugins\dsh-greatwall-agent\greatwall-agent\bin\gw_mcp_server.py'
```

插件已经为子进程设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`、`PYTHONUNBUFFERED=1`、`PYTHONDONTWRITEBYTECODE=1`（最后一项避免在安装目录写 `__pycache__`）；如果自定义 `pythonPath` 指向包装脚本，请确保它不向 stdout 打印任何东西。

另外两个相关设置：`toolCallTimeoutMs: 600000`（单次调用 10 分钟）与 `failOnStartupError: false`（Python 缺失不会拖垮整个 profile，只是没有工具）。

### 4.3 门禁误伤（关闭清洁室守卫）

```yaml
- id: greatwall-agent
  name: 'dsh-greatwall-agent'
  config:
    pythonPath: 'python'
    cleanroomGate: false
```

`cleanroomGate: false` 时**完全不注册**守卫（不是“宽松模式”）。这只应作为临时排障手段：门禁保护的是 `.kernel_vault`（评测真值与 HMAC 密钥）与只读档案馆。

### 4.4 技能缺失

插件激活时会记录：

```text
[dsh-greatwall-agent] core=... python=... mcp=... skills=greatwall-campaign gate=on
```

- `skills=none`：宿主没有可用的 skills 服务（`ctx.get("skills")` 为空），此时 MCP 与门禁不受影响。
- 日志出现 `skill pack problems`：说明 `greatwall-agent/skills/greatwall-campaign/SKILL.md` 的 frontmatter 或名称校验失败（`skillpack.js` 会给出原因，如 `NO_SKILL_MD`、`NAME_DIRECTORY_MISMATCH`、`INVALID_NAME`）。

### 4.5 版本与安装通道问题

- DSH 版本需满足 `>=0.2.2-rc.1 <0.3.0-0`；否则安装/启动会被 `engines` 拒绝。
- `desktop` 等 Electron 托管 profile 不能用 `dsh plugin` 管理（实测报错见 2.1）。
- CLI 安装依赖 pnpm；缺 pnpm 时先安装 pnpm 或用 Desktop 通道。

---

## 五、卸载

**DSH Desktop（Electron 托管 profile）**：在应用内插件管理中移除 `dsh-greatwall-agent`。移除后 `dsh.profile.bundles` 中该条目与 `link:` 依赖一并消失。

**CLI 托管 profile**：

```powershell
dsh plugin --profile <profile-name> remove dsh-greatwall-agent
```

卸载行为说明：

- 插件的三项注册（MCP 挂载、技能、门禁）都是 Cordis effect，插件卸载时自动撤销；
- 卸载**不会**删除你的攻关工作区（`.kernel_vault/`、`shared_readonly/`、`worktrees/`）与 `final_delivery/`；
- 卸载**不会**改动 `greatwall-agent/` 内核文件。

---

## 六、升级

- **npm 包**：`dsh plugin --profile <profile-name> add dsh-greatwall-agent@<version>`（版本需满足 `engines.dsh`）。
- **本地 link 安装**：更新工作区目录后重启 DSH 会话即可；link 不会复制文件。
- 升级后重跑 3.1–3.7 的验证项，尤其是 `node tools/verify-core.mjs`（升级不得改动内核）。

---

## 七、运行随包的端到端测试

测试文件：`greatwall-agent/tests/test_plugin_e2e.py`（随包逐字节提供，18 个内核文件之一）。它覆盖 10 个方向：Phase 0 EDA + 候选基线竞技、AST 微创替换、AST 反作弊契约、`PreToolUse` 门禁矩阵、五件套遗产/引用计数/撤回树、60 步锁与 `BarrierProof`、软清栈与共性死因补丁、差分互测与错题平反、Windows Job Object 与并发文件锁、MCP 9 工具全协议与终局防吹牛。

```powershell
Set-Location 'D:\Documents\deepseek harness\长城Agent_框架设计'
$env:PYTHONUTF8 = '1'
python -W default 'plugins\dsh-greatwall-agent\greatwall-agent\tests\test_plugin_e2e.py'
```

- 需要能运行 Python 3 的 `python`；不需要安装任何第三方包，也不需要联网。
- 测试使用系统临时目录（`tempfile.mkdtemp`），结束后自动清理；不会写入设计仓库。
- `test_09` 依赖 Windows Job Object，因此该套件的完整通过结论仅对 Windows 成立。
- 归档日志见 [`audit/e2e_run.log`](audit/e2e_run.log)（该文件是重定向产物，中文可能因控制台代码页显示为乱码，但 `Ran 10 tests ... OK` 结论可读）。

---

## 八、附录：本轮实测输出

```text
PS> node --version
v24.20.0
PS> python --version
Python 3.14.7
PS> node plugins/dsh-greatwall-agent/tools/verify-core.mjs
OK: 18 core files match core-manifest.sha256 (byte-identical Antigravity tree)
PS> python -W default plugins/dsh-greatwall-agent/greatwall-agent/tests/test_plugin_e2e.py
Ran 10 tests in 2.882s
OK
```

MCP 手工探测：

```text
PS> '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python plugins\dsh-greatwall-agent\greatwall-agent\bin\gw_mcp_server.py
{"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "greatwall-agent", "version": "4.2.0"}, "capabilities": {"tools": {}}}}
```

清洁室门禁实拦（DSH 会话内）：

```text
read  D:\...\.kernel_vault\...            → 🔒 [长城 Agent 清洁室隔离门禁] 严禁直接读取或修改 `.kernel_vault` ...
pwsh  'shared_readonly' > $env:TEMP\...   → 🔒 [长城 Agent 只读档案馆门禁] 严禁通过终端命令重定向或修改 `shared_readonly/` ...
read  worktrees\slot_01\..\slot_02\...    → 🔒 [长城 Agent 跨孤岛防偷看门禁] 严禁通过 `../slot_*` ...
pwsh  slot_01_node-a + slot_02_node-b     → 🔒 [长城 Agent 跨孤岛防偷看门禁] 检测到单次操作同时引用多个孤岛槽位 [...]
pwsh  Write-Output 'ordinary'             → 正常输出
```
