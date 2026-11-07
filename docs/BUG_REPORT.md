# 长城 Agent V4.2 · Python 核心缺陷审计报告（DSH 移植前）

- **审计对象**：`plugins/greatwall-agent/`（Antigravity 原插件，**只读**，未修改任何字节）
- **审计目的**：Python 核心（`lib/`、`bin/gw_mcp_server.py`）将**逐字节**进入 DSH 移植包，因此所有缺陷只报告、不修复
- **交付物**：本报告 + `docs/audit/` 下的探针脚本、原始日志与结构化结果
- **审计日期**：2026-11-07；**平台**：Windows 11 + PowerShell 7；**Python**：3.14.7（`C:\Users\wangy\AppData\Local\Programs\Python\Python314\python.exe`）

> **一句话结论**：移植链路本身可用（DSH MCP 桥实测 2 个工具调用成功、九工具战役 20 步全绿、自带 e2e 10/10 通过），
> 但核心存在 **2 个 P0 级 MCP 阻塞缺陷**与 **10 个 P1 级真实缺陷**。其中「评测分数就是被测代码自己的输出」
> 与「清洁室没有 OS 级隔离」使 V4.2 文档中的**防吹牛 / HMAC 防伪 / 物理隔离**三项安全承诺在实现层面不成立；
> 移植后若原样对外宣传，会误导使用者。

---

## Top findings（按严重度排序，先看这 12 条）

| # | 级别 | 缺陷 | 位置 | 证据 |
|---|---|---|---|---|
| 1 | **P0** | 收到任何**非对象** JSON 帧（JSON-RPC 批量数组、`null`、数字、字符串）MCP 服务进程直接 `AttributeError` 崩溃退出（exit 1），桥随之断掉 | `bin/gw_mcp_server.py:487` | `audit/crash_stderr_01..04_*.txt`、`audit/mcp_conformance_result.json` |
| 2 | **P0** | 工具业务失败（`status: ERROR / REJECTED_BY_AST_AUDITOR / LEGACY_REJECTED / DELIVERY_BLOCKED_PLACEHOLDERS / SLOTS_FULL / FORGED_RECEIPT_DETECTED / BLOCKED_BY_BARRIER_PROOF`）**一律以 `isError:false` 返回**，“失败”被 DSH 当成“成功” | `bin/gw_mcp_server.py:512-525`（`523` 行写死 `false`） | `audit/mcp_conformance_result.json`、`audit/campaign_result.json` |
| 3 | **P1** | **评测分数 = 被测代码自己的返回值**；HMAC 只是给自报数字盖章。`evaluate()` 直接 `return {"frozen_score": 1e9}` 即拿到合法签名收据并 PARETO_PROMOTE | `lib/evaluator.py:523-537`、`831-849`、`856-863` | `audit/security_result.json` C1/C2；`audit/campaign_result.json` s0=20277 |
| 4 | **P1** | **清洁室无 OS 级隔离**：被评测代码可写出孤岛、读取 `.kernel_vault/hmac_secret.key`（实测逐字节一致），HMAC 密钥对被测代码并不保密 | `lib/evaluator.py:502-508` + `lib/sandbox.py:469-523` | `audit/security_result.json` B1 |
| 5 | **P1** | `gw_archive_query` 的 `itemId` **路径穿越**：`../../../../任意文件名` 或绝对路径即可读取档案馆外任意 `.py` 源码（含其他槽位/宿主文件） | `lib/archive.py:809-814` | `audit/security_result.json` A1 |
| 6 | **P1** | `gw_submit_legacy` **先入库、后验签**：伪造收据虽被拒，但原语已复制进 `archive/ledger/primitives/`、已登记 manifest、死胡同记录已写入——档案馆被污染 | `lib/engine.py:629-653` | `audit/submit_order_result.json` H1 |
| 7 | **P1** | `BarrierProof` **只要脚本 exit=0 就认证“不可能”**：一个 `print('nothing is proven here')` 就能永久封禁整个方法族；且 `counterexample_script` 未做路径校验，可执行孤岛外任意 `.py` | `lib/archive.py:597-621` | `audit/security_result.json` E1/E2 |
| 8 | **P1** | **原语入库无 AST 安全审计**：`_audit_and_test_primitive` 声称审计，实际直接把节点代码 `exec_module` + 跑 `test_*`，`import os` / 任意系统调用全部放行 | `lib/archive.py:669-726` | `audit/security_result.json` F1 |
| 9 | **P1** | `hook_gate.py` **只认 Antigravity 的 `toolCall.args.Path/CommandLine` 与 `read_file/write_file/edit_file/run_command`**；DSH 参数形状（`file_path`/`command`/`text`）下**全部放行**；另有大小写、绝对路径、`Copy-Item`、`python -c` 等 14 条实测绕过；解析失败一律 fail-open | `bin/hook_gate.py:25-27,42,47-56,64-69,88-90` | `audit/hook_gate_result.json`（14 条 bypass） |
| 10 | **P1** | AST 微创替换**整文件重写换行**（LF 文件在 Windows 上整体变 CRLF）、UTF-8 BOM 被误判语法错误、GBK 文件抛未捕获 `UnicodeDecodeError` | `lib/sandbox.py:685,754,789` | `audit/runtime_result.json` S1/S1b/S2/S3 |
| 11 | **P1** | `hard_fork` 不校验祖先提交是否存在：`ancestorCommit="NO_SUCH_COMMIT"` 返回 `status:OK` 但孤岛 `src/` 为空（代码全丢）；同一秒内两次分叉产生**相同 lineage_id**（第二次覆盖第一次） | `lib/engine.py:862-863`、`lib/sandbox.py:607-615` | `audit/campaign_result.json` step 16/17 |
| 12 | **P1** | `mcp_config.json` / `hooks.json` 硬编码本机绝对路径（`C:\Users\wangy\...`、Python314 安装路径），**不可随包分发**；DSH 侧必须重新生成注册信息 | `mcp_config.json:4-10`、`hooks.json:8-10` | 文件原文（见 P1-10） |

---

## 0. 审计环境与完整性声明

### 0.1 完整性证明（原件零改动）

| 检查 | 命令 | 结果 |
|---|---|---|
| 原件全树哈希前后一致 | 见 `audit/orig_tree_hashes_before.txt`（23 个文件）与审计结束时的逐文件 SHA-256 对比 | `TREE UNCHANGED: 23 files identical to snapshot` |
| 原插件 git 工作区干净 | `git status --porcelain -- plugins/greatwall-agent` | 输出为空 |
| 移植副本与原件逐字节一致 | `node plugins/dsh-greatwall-agent/tools/verify-core.mjs` | `OK: 18 core files match core-manifest.sha256 (byte-identical Antigravity tree)` |

> 说明：原插件目录里本来就有未被 git 跟踪的 `lib/__pycache__/*.pyc`。为不改动原件，本审计所有探针均以
> **`python -B`（或 `PYTHONDONTWRITEBYTECODE=1`）**运行，避免重写 `.pyc`；动态实验全部在 `%TEMP%` 下创建临时工作区。

### 0.2 本次实际执行的命令（全部可复现）

```powershell
# 1) 自带 e2e 测试（加 -B 仅为不触碰原件 __pycache__）
python -B -W default "plugins/greatwall-agent/tests/test_plugin_e2e.py" -v

# 2) MCP 协议一致性
python -B plugins/dsh-greatwall-agent/docs/audit/probe_mcp_conformance.py

# 3) 九工具战役全链路（JSON-RPC 驱动，工作区在 %TEMP%）
python -B plugins/dsh-greatwall-agent/docs/audit/probe_campaign.py

# 4) 安全/越权/信任链
python -B plugins/dsh-greatwall-agent/docs/audit/probe_security.py

# 5) 运行时（微创替换、路径牢笼、跨进程锁、Job Object）
python -B plugins/dsh-greatwall-agent/docs/audit/probe_runtime.py

# 6) hook_gate 决策矩阵（25 例）
python -B plugins/dsh-greatwall-agent/docs/audit/probe_hook_gate.py

# 7) 静态局限（黑名单误杀、伪动态变量、subprocess 放行、指标解析）
python -B plugins/dsh-greatwall-agent/docs/audit/probe_static_claims.py

# 8) submit_legacy 验签顺序
python -B plugins/dsh-greatwall-agent/docs/audit/probe_submit_order.py

# 9) 未初始化即分配槽位
python -B "$env:TEMP\gw_uninit_probe.py"
```

### 0.3 总览结果

| 测试 | 结果 |
|---|---|
| 自带 e2e（`test_plugin_e2e.py`） | **10/10 `ok`，`Ran 10 tests in 2.960s`，exit 0**（`audit/e2e_run.log`） |
| MCP 协议一致性（25 项检查） | **19 PASS / 5 FAIL**；失败项即 P0-1（4 个崩溃帧）+ P0-2（错误语义） |
| 九工具战役 smoke test | **20 步全链路完成，0 个 `isError:true`，服务端 exit 0**；但其中 3 步是“业务拒绝却报成功”（P0-2） |
| 安全/越权探针 | **9/9 全部复现** |
| 运行时探针 | **13/13 全部复现** |
| hook_gate 决策矩阵 | 25 例中 **14 条应拦未拦（bypass）**，0 条误杀，畸形输入 4/4 fail-open |
| 静态局限探针 | 5/5 复现 |
| 提交顺序探针 | 复现：伪造收据被拒，但档案馆已被写脏 |
| DSH 真实 MCP 桥 | `gw_init_campaign` + `gw_archive_query` 实测成功（`audit/dsh_bridge_e2e.md`） |

---

## 1. P0（阻塞 DSH 移植）

### P0-1 非对象 JSON 帧让 MCP 服务进程崩溃退出（MCP 桥断路）

- **位置**：`bin/gw_mcp_server.py:487`（主循环 `477-548`）
- **症状**：`json.loads(line)` 成功后无类型校验，`request.get("id")` 对 `list / None / int / str` 直接抛
  `AttributeError`；异常未被捕获，进程以 exit code 1 退出（traceback 打到 stderr）。受影响的合法 JSON 帧包括
  **JSON-RPC 批量请求**（`[{...}]`）与任何标量帧。
- **复现**：

```powershell
python -B plugins/dsh-greatwall-agent/docs/audit/probe_mcp_conformance.py
# 只看“survives frame”系列输出
```

  单帧复现（等价于探针内部行为）：向 `gw_mcp_server.py` 的 stdin 先写 `initialize`，再写一行
  `null` / `123` / `"hello"` / `[{"jsonrpc":"2.0","id":1,"method":"tools/list"}]`。

- **期望 vs 实际**：

| 帧 | 期望 | 实际 |
|---|---|---|
| `[{"jsonrpc":"2.0","id":1,"method":"tools/list"}]` | 返回 `-32600 Invalid Request` 或批量响应，进程存活 | 无任何响应，进程退出 1 |
| `null` / `123` / `"hello"` | 返回 `-32600` | 无任何响应，进程退出 1 |

- **证据**（完整 traceback 已落盘）：

```
audit/crash_stderr_01_JSON_array__JSON_RPC_batch_.txt
  File "...\plugins\greatwall-agent\bin\gw_mcp_server.py", line 552, in <module>
    main()
  File "...\gw_mcp_server.py", line 487, in main
    req_id = request.get("id")
AttributeError: 'list' object has no attribute 'get'

audit/crash_stderr_02_JSON_null.txt   -> AttributeError: 'NoneType' object has no attribute 'get'
audit/crash_stderr_03_JSON_number.txt -> AttributeError: 'int' object has no attribute 'get'
audit/crash_stderr_04_JSON_string.txt -> AttributeError: 'str' object has no attribute 'get'
```

  结构化结果：`audit/mcp_conformance_result.json` 中 4 条 `"survives frame: ..."` 记录均为
  `"alive_after_frame": false, "exit_code": 1`。

- **对 DSH 移植的影响**：核心逐字节不可改，**移植层不能直接把这个进程交给 DSH 桥**。一次批量帧/损坏帧就会让
  9 个工具整批失联，必须重启 MCP 连接；在无人值守长程任务里等于整条战役中断。移植层需要：① 在前置代理里做
  “非对象帧 → 丢弃/返回 -32600”的守卫并自动重启；或 ② 在 DSH 侧以可重启的 supervisor 托管该服务。
- **建议（不改原码）**：移植包附带一个极薄的 stdio 代理守卫（逐行 `json.loads`，非 dict 则回
  `{"jsonrpc":"2.0","id":null,"error":{"code":-32600,...}}` 并继续），或把该缺陷作为已知限制写进 DSH 插件文档。

---

### P0-2 业务失败一律 `isError:false`，MCP 错误语义失效

- **位置**：`bin/gw_mcp_server.py:512-525`（`523` 行 `"isError": False` 写死在成功分支）
- **症状**：`handle_tool_call` 绝大多数业务失败**不抛异常**，而是返回 `{"status": "ERROR"/"REJECTED_..."}` 字典；
  服务器只在 **异常** 分支把 `isError` 设为 `true`。因此所有“业务拒绝”在协议层都是成功结果。实测失败却报成功的
  状态至少包括：`ERROR`、`REJECTED_BY_AST_AUDITOR`、`LEGACY_REJECTED`、`DELIVERY_BLOCKED_PLACEHOLDERS`、
  `SLOTS_FULL`、`BLOCKED_BY_BARRIER_PROOF`、`FORGED_RECEIPT_DETECTED`、`COMMITMENT_LOCK_ACTIVE`。
- **复现**：

```powershell
python -B plugins/dsh-greatwall-agent/docs/audit/probe_mcp_conformance.py
# 关注：[FAIL] tool-level status=ERROR is reported as isError=true
```

  原始响应：`{"jsonrpc":"2.0","id":9,"result":{"content":[{"type":"text","text":"{\n  \"status\": \"ERROR\",\n  \"message\": \"找不到活跃槽位: slot_99_missing\"\n}"}],"isError": false}}`
- **期望 vs 实际**：期望 `result.isError == true` 且 `content` 说明失败；实际 `isError == false`。
- **证据**：
  - `audit/mcp_conformance_result.json` → `"tool-level status=ERROR is reported as isError=true"`：`isError=false`
  - `audit/campaign_result.json` → `gw_evaluate_slot/AST-gate-reject`（`status: REJECTED_BY_AST_AUDITOR`，`isError: false`）、
    `gw_compile_delivery/placeholder-blocked`（`status: DELIVERY_BLOCKED_PLACEHOLDERS`，`isError: false`）
- **对 DSH 移植的影响**：DSH 以 MCP `isError` 判断工具调用是否失败。现状下**模型会把“被 AST 拒绝”“槽位已满”
  “收据伪造”“交付被拦截”当成成功**，继续推进错误流程；这是移植后最容易被用户直接感知的语义错误。属于“不解决
  就不能如实交付”的 P0，但同样受“核心不可改”约束，必须在移植层包装（读取 payload 的 `status` 字段重新映射
  `isError`，或改成抛 `ToolError`）。
- **建议**：移植层增加 `status` → `isError` 的映射层；拒绝状态列白名单至少覆盖上述 8 个。

---

## 2. P1（真实缺陷）

### P1-1 评测分数完全来自被测代码自身，HMAC「防伪」只是给自报数字盖章

- **位置**：`lib/evaluator.py:523-537`（解析指标）、`831-849`（`evaluate()` 返回值直接当分数）、`856-863`（`solve()` 的返回值直接当分数）；承载链：`lib/engine.py:352-362, 586-599`；`lib/archive.py:732-772`
- **症状**：内置评测 harness 的“得分”定义是：
  1. 候选模块定义 `evaluate()`：`for k, v in res.items(): metrics[k] = float(v)` —— **候选自己说什么就是什么**；
  2. 候选模块定义 `solve()`：把 `solve([10,25,-5,...])` 的返回值当 `frozen_score`；
  3. 引擎没有任何真值标签/隐藏评测集参与打分，之后对这份数字签名、入榜、参与分级。
- **复现（动态，已落盘）**：

```powershell
python -B plugins/dsh-greatwall-agent/docs/audit/probe_security.py
```

  - C1：候选 `def evaluate(): return {'frozen_score': 1e9, 'live_score': 1e9, ...}` → 引擎返回
    `anchor_s0_score = 1000000000.0`，`triage_tier = PARETO_PROMOTE`，且收据带 `hmac_sha256_signature`。
  - C2：候选在 `atexit` 里补打一行伪造 `__GW_METRICS_JSON__:{"frozen_score":777.0,...}` → 真实 `solve()` 只返回
    `1.0`，最终收据却是 `777.0`（解析器取“最后一行”）。
  - 战役实测（`audit/campaign_result.json` step 2）：两个“候选基线”分别是 `return float(sum(inputs))` 与
    `return float(sum(v*v for v in inputs))`，引擎把后者输出 **20277.0** 当作“零号强基线 s_0 得分”。
- **期望 vs 实际**：期望评测分由引擎侧真值/独立评测集计算，被测代码无法自证；实际完全自证。
- **证据**：`audit/security_result.json`（C1/C2）、`audit/campaign_result.json`（`anchor_s0_score: 20277.0`、
  `candidate_tournament_log`）、`audit/evaluator` 行号见上。
- **对 DSH 移植的影响**：任何“比赛/科研”任务在 DSH 上都会把“模型自己写的分数”当真值排行榜；
  `gw_submit_legacy` 的 HMAC 校验、排行榜、最终交付表全部建立在不可信输入上。移植后如果保留“防吹牛/防伪成绩单”
  的对外描述，属于**功能与宣传不符**。
- **建议**：引擎侧持有评测集与评分函数（在引擎进程或独立 runner 中计算，候选只提供 `predict()` 输出）；
  分数绝不允许由候选 `return`。若短期做不到，DSH 插件文档必须把“HMAC 防伪”降级为“防手工改文件”，不得宣称防作弊。

---

### P1-2 清洁室没有 OS 级隔离：被测代码可越界读写并读取 HMAC 密钥

- **位置**：`lib/evaluator.py:502-508`（`run_bounded_subprocess` 只做环境变量清洗）、`lib/sandbox.py:293-326`（`build_sanitized_env`）、`lib/sandbox.py:469-523`
- **症状**：`run_bounded_subprocess` 只是“清环境变量 + Job Object 限额 + PIPE 捕获”，**没有任何文件系统/网络/
  进程级沙箱**。被评测的候选代码以当前用户身份运行，可 `open('../../任意路径')`、`os.remove`、
  `subprocess.run`（AST 也不拦 `subprocess`，见 P2-10）。因此：
  - 可读取 `.kernel_vault/hmac_secret.key`（HMAC 签名密钥），实测读到的内容与密钥文件逐字节一致；
  - 可写出孤岛（在工作区根留下 `pwned_outside_island.txt`）；
  - 可读取其他槽位代码、篡改 `state_graph.json`、删除档案馆。
- **复现**：

```powershell
python -B plugins/dsh-greatwall-agent/docs/audit/probe_security.py
# [CONFIRMED] B1 ...
```

  候选代码（`candidateBaselines` 的 `solve`）：

```python
import pathlib
def solve(inputs):
    ws = pathlib.Path.cwd().parent.parent
    secret = (ws / '.kernel_vault' / 'hmac_secret.key').read_text(encoding='utf-8').strip()
    (ws / 'pwned_outside_island.txt').write_text('secret=' + secret, encoding='utf-8')
    return float(sum(inputs))
```

  输出：`"pwned_file_created_outside_island": true, "pwned_content_matches_vault_secret": true`。
- **期望 vs 实际**：期望 `.kernel_vault`（含 HMAC 密钥）对被测代码不可读、孤岛外不可写；实际完全可读可写。
- **证据**：`audit/security_result.json`（B1）。
- **对 DSH 移植的影响**：`hook_gate` 只拦“Agent 的读写工具调用”，**拦不住被评测进程本身**。V4.2 中“物理隔离/
  清洁室/特权保险箱”的表述在 DSH 上不成立；如果 DSH 插件把它当安全边界使用（例如用 HMAC 判定用户成果真实性），
  会被自证代码绕过。
- **建议**：真要做隔离，需要 OS 级手段（低权限账户/AppContainer/SMB 只读挂载/容器）；否则文档必须明确
  “清洁室 = 逻辑隔离（防误操作），非安全边界”。

---

### P1-3 `gw_archive_query`（get_l2_item）路径穿越读取任意 `.py`

- **位置**：`lib/archive.py:807-814`
- **症状**：`itemId` 直接拼进 `primitives_dir / f"{item_id.removeprefix('prim_')}.py"`，随后 `read_text` 返回内容。
  无 jail、无 `resolve()` 包含性校验；`../` 或绝对路径均可逃逸（追加 `.py` 后缀也挡不住前缀里的目录穿越）。
- **复现**：

```powershell
python -B plugins/dsh-greatwall-agent/docs/audit/probe_security.py
# [CONFIRMED] A1 ...
```

  实测请求（MCP JSON-RPC `tools/call`）：

```json
{"name":"gw_archive_query","arguments":{"workspaceRoot":"<tmp>/ws","action":"get_l2_item","itemId":"../../../../outside_workspace_secret"}}
```

  响应 `content` 为工作区外文件的完整内容；绝对路径 `itemId: "<tmp>/outside_tmp_secret"` 同样成功。
- **期望 vs 实际**：期望只允许访问 `shared_readonly/archive/ledger/primitives/` 下的原语；实际可读磁盘任意
  `*.py`（其他槽位未验收代码、宿主源码）。
- **证据**：`audit/security_result.json`（A1，含响应 path 字段与命中内容）。
- **对 DSH 移植的影响**：这是**唯一一个不需要改核心就能在 MCP 层直接利用**的越权读；DSH 上模型可通过
  `gw_archive_query` 读取其他分支/宿主代码，绕过 `hook_gate` 的“跨槽位偷看”规则（hook 只管文件工具，不管 MCP 工具）。
- **建议**：移植层对 `itemId` 做白名单正则（`^[A-Za-z0-9_.-]+$`）并拒绝含 `/`、`\`、`..`、盘符的值。

---

### P1-4 `submit_legacy` 先入库后验签，伪造收据也能污染档案馆

- **位置**：`lib/engine.py:629-653`（`629` 行调用 `validate_and_admit_legacy`，`648` 行才校验 HMAC）
- **症状**：`validate_and_admit_legacy` 内部在校验通过后**立即执行入库副作用**（复制原语、写 manifest、写
  claims/barrier/bounty/record、跑 Meta-Pattern 补丁、刷 L0 索引）；而 HMAC 验签发生在其后。伪造
  `metrics_receipt.json` 时函数返回 `FORGED_RECEIPT_DETECTED`，但副作用已经发生且**不回滚**。
- **复现**：

```powershell
python -B plugins/dsh-greatwall-agent/docs/audit/probe_submit_order.py
```

  输出（节选）：

```json
{
  "submit_status": "FORGED_RECEIPT_DETECTED",
  "side_effects_after_forged_receipt": {
    "primitive_copied_into_archive": true,
    "primitive_registered_in_manifest": true,
    "record_blacklist_written": true,
    "island_still_present": true,
    "state_slot_still_active": true
  }
}
```

- **期望 vs 实际**：期望先验签，失败则零副作用；实际原语已进入全局档案馆（其他节点可 import）、manifest 已登记、
  死胡同记录已写入，且槽位仍活跃（可以反复刷）。
- **证据**：`audit/submit_order_result.json`（H1）。
- **对 DSH 移植的影响**：节点伪造收据被“发现”并不代表安全——污染已经扩散到跨血统原语库，后续节点会 import 恶意/错误
  原语。移植层无法在 MCP 层补救，只能文档告警并在 DSH 侧加“提交前自查 + 档案馆只追加校验”。
- **建议**：调整顺序为先验签、再入库（核心不可改 → 移植层在调用 `gw_submit_legacy` 前先自行验签，或禁止跨血统引用
  未复核原语）。

---

### P1-5 `BarrierProof` 认证只看 exit=0；反例脚本可越界执行

- **位置**：`lib/archive.py:574-621`（`597` 行拼路径、`601-607` 行跑脚本、`608-609` 行只判 `exit_code != 0`）；
  调用点 `lib/archive.py:381-386`、封禁点 `lib/engine.py:452-457`（`has_verified_barrier_for_family`）
- **症状**：
  1. 任何退出码为 0 的脚本都会被认证为“该正交方法族不可能”的证明，`impossibility_statement` 内容不做语义校验；
     一旦入库，`gw_allocate_slot` 对该 family **永久返回 `BLOCKED_BY_BARRIER_PROOF`**（拒绝分配算力）。
  2. `counterexample_script` 直接 `(island_dir / script_rel).resolve()`，`../` 可指向孤岛外任意 `.py` 并被执行。
- **复现**：

```powershell
python -B plugins/dsh-greatwall-agent/docs/audit/probe_security.py
# [CONFIRMED] E1 ... / [CONFIRMED] E2 ...
```

  E1：`proof_noop.py = print('nothing is proven here')` → `admitted_barrier_proofs=["BARRIER-AUDIT-1"]`，
  随后 `allocate_slot("FAM-02", ...)` → `BLOCKED_BY_BARRIER_PROOF`。
  E2：`counterexample_script="../escaped_barrier.py"` → 返回 `(True, 'OK')`，孤岛外脚本被执行（marker 文件存在）。
- **期望 vs 实际**：期望“死路证明”至少要验证反例脚本确实对目标方法族做了证伪实验，且脚本必须位于孤岛内；实际只看
  exit code、脚本可越界。
- **证据**：`audit/security_result.json`（E1/E2）。
- **对 DSH 移植的影响**：一个节点（或任何能提交遗产包的流程）可以**永久瘫痪某个方法族的调度**（DoS / 策略性封锁）；
  也可借反例脚本执行路径读取/写入任意位置（结合 P1-2 的“清洁室无效”放大）。这是 DSH 长程任务里最容易被“策略性偷懒”
  利用的漏洞：用空证明提前放弃方法族可绕过 60 步深挖锁。
- **建议**：移植层把“BarrierProof 免死”视为不可信输入（人工复核后才能封禁 family）；`counterexample_script` 做
  realpath 包含性校验。

---

### P1-6 原语入库“AST 审计”名不副实，节点代码被直接执行

- **位置**：`lib/archive.py:669-726`（`676-704` 只检查 `def`/docstring/`test_*` 存在性；`706-714` 直接拼 runner；
  `715-724` 在沙箱进程里 `exec_module` 并调用 `test_*`）
- **症状**：文档字符串与 `validate_and_admit_legacy` 注释均声称“AST 审计 + 独立沙箱单元测试”，但代码里
  **没有任何禁止导入/禁止调用检查**（`ASTCodeInspector.inspect_code` 没有被调用）。入库瞬间就会执行节点提交的
  `legacy_out/primitives/*.py`（含 `test_*`），因此任意 `import os / pathlib / subprocess` 的副作用都会发生。
- **复现**：

```powershell
python -B plugins/dsh-greatwall-agent/docs/audit/probe_security.py
# [CONFIRMED] F1 ...
```

  探针原语 `evil.py` 在 `test_helper()` 里写出 marker 文件；结果 `admitted=true`、`marker_created=true`。
- **期望 vs 实际**：期望与 `gw_evaluate_slot` 同样过 AST 反作弊（禁 `ctypes/socket/eval` 等）；实际无任何审计。
- **证据**：`audit/security_result.json`（F1）。
- **对 DSH 移植的影响**：`gw_submit_legacy` 是 DSH 插件对外暴露的工具；任何节点都能通过“提交原语”令宿主执行任意
  Python（当前用户权限）。这在“无人值守 + 多子代理”场景下等于把宿主交给模型。
- **建议**：移植层在调用 `gw_submit_legacy` 前，对 `legacy_out/primitives/*.py` 走一遍 `ASTCodeInspector` 的
  禁止导入/调用检查；或把原语入库改为显式人工审批。

---

### P1-7 `hook_gate.py` 对 DSH 参数形状完全失效，且存在 14 条实测绕过与 fail-open

- **位置**：`bin/hook_gate.py:20-31`（只读 `toolCall.args.Path` / `TargetFile` / `CommandLine` 与
  `read_file/write_file/edit_file/replace_file_content/multi_replace_file_content/run_command`）、
  `34-38`（`.kernel_vault`）、`41-56`（shared_readonly 写）、`59-69`（跨槽位）、`74-90`（空 stdin / 异常 → allow）
- **症状**：
  1. **DSH 工具形状下永不生效**：DSH 的 `read`/`write`/`edit` 用 `file_path`，shell 用 `command`；
     `target_path_str` 与 `cmd_line` 都是空串，`combined_text` 为空 → 第 30 行快速放行。**包括对
     `.kernel_vault` 的读写**。
  2. **Windows 大小写**：`.KERNEL_VAULT`、`SHARED_READONLY`、`../SLOT_` 均放行（Windows 路径大小写不敏感）。
  3. **黑名单不全**：`Copy-Item`、`New-Item`、`python -c open(...)`、`tee` 等写入 `shared_readonly` 全部放行。
  4. **绝对路径跨槽位**：`D:\ws\worktrees\slot_02_node-002\src\main.py` 只含一个 slot、无 `../slot_` → 放行。
  5. **环境变量/通配符**：`($env:USERPROFILE + '\.kernel' + '_vault\x.json')`、`.kernel_*/...` 放行。
  6. **任何解析异常 fail-open**：空 stdin、非法 JSON、顶层数组、缺 `toolCall` 一律 `{"decision":"allow"}`。
- **复现**：

```powershell
python -B plugins/dsh-greatwall-agent/docs/audit/probe_hook_gate.py
# bypasses(14): H07 H08 H09 H10 H11 H12 H13 H14 H15 H16 H17 H18 H19 H20
# false-deny(0)
```

- **期望 vs 实际**：

| 用例 | 期望 | 实际 |
|---|---|---|
| H07 DSH `read` + `file_path=...\.kernel_vault\state_graph.json` | deny | **allow** |
| H08 DSH `write` + `file_path=...\shared_readonly\x.txt` | deny | **allow** |
| H09 DSH `edit` + `.kernel_vault\hmac_secret.key` | deny | **allow** |
| H10 DSH `pwsh` + `command="echo x > shared_readonly/a.txt"` | deny | **allow** |
| H11/H12/H13 大写敏感目录 | deny | **allow** |
| H14 `Copy-Item` 写 shared_readonly | deny | **allow** |
| H15 `python -c "open('shared_readonly/x','w')..."` | deny | **allow** |
| H17 绝对路径读隔壁槽位 | deny | **allow** |
| H21-H24 空 stdin / 非法 JSON / 数组 / 缺字段 | deny 或明确错误 | **allow**（fail-open） |

- **证据**：`audit/hook_gate_result.json`（25 例完整 payload/decision）、`audit/hook_gate_probe.log`。
- **对 DSH 移植的影响**：**不能把 `hook_gate.py` 当 DSH 的 PreToolUse hook 使用**。DSH 的 hook/guard 必须按
  DSH 的工具名与参数 schema 重写（`file_path`/`command`/`text`），并且默认 fail-closed；移植包的
  `lib/gate.js` 若只复刻字符串匹配，会继承同样的绕过。特别注意：`hook_gate` 只拦“工具调用”，拦不住 P1-2 的
  被评测进程。
- **建议**：DSH gate 用路径解析（`realpath` + 包含性判断）而不是子串匹配；deny 规则覆盖所有写工具与 shell；
  解析失败一律 deny（或仅对白名单路径放行）。

---

### P1-8 AST 微创替换：整文件换行重写 / BOM 误杀 / GBK 崩溃

- **位置**：`lib/sandbox.py:685`（`script_path.read_text(encoding="utf-8")`，通用换行模式）、
  `lib/sandbox.py:754-756`（重排缩进）、`lib/sandbox.py:789`（`write_text`，Windows 下 `\n`→`\r\n`）
- **症状**：
  1. `read_text` 默认 `newline=None` → CRLF/LF 全部归一化为 `\n`；`write_text` 在 Windows 又把 `\n` 翻译成
     `\r\n`。结果：**一次微创替换把整个文件的行尾改掉**（LF 文件变 CRLF），未被触碰的函数字节也变了，
     但工具只报“已原位微创替换代码块 'solve'”——直接违反“冻结其余外围代码”的设计承诺。
  2. UTF-8 BOM 文件（Windows 常见）被 `ast.parse` 判为 `invalid non-printable character U+FEFF`，工具报
     “原脚本存在语法错误”并拒绝——但 CPython 自己可以正常运行该文件。
  3. 非 UTF-8（如 GBK）源文件 `read_text` 抛 `UnicodeDecodeError`，未捕获，直接抛穿到 MCP 工具层。
- **复现**：

```powershell
python -B plugins/dsh-greatwall-agent/docs/audit/probe_runtime.py
# [CONFIRMED] S1 / S1b / S2 / S3
```

  - S1：CRLF 文件替换 `solve` 后，`untouched_marker` 前的内容字节发生变化（`untouched_function_region_bytes_changed: true`）。
  - S1b：`def solve(x):\n    return 1\n...` 一次替换后 `contains_crlf: true`。
  - S2：`python -B bom_app.py` 退出码 0，但 `surgical_replace_block` 返回 `False, "原脚本存在语法错误: invalid non-printable character U+FEFF"`。
  - S3：GBK 文件 → `UnicodeDecodeError('utf-8', b'# \xd6\xd0...', 2, 3, 'invalid continuation byte')`。
- **期望 vs 实际**：期望只改目标行、保持文件编码/换行/BOM 原样，不支持编码时返回结构化错误；实际整文件重写、BOM
  误杀、GBK 崩工具。
- **证据**：`audit/runtime_result.json`（S1/S1b/S2/S3）。
- **对 DSH 移植的影响**：DSH 上的模型经常用 `write` 生成 LF 文件、也可能带 BOM；每次 `gw_surgical_replace` 都会把
  文件改写到平台换行，导致 `diff.patch` 体积/内容与真实改动不一致（虽然 `generate_unified_diff` 也做了归一化，表象被
  掩盖），节点还会因其“冻结外围代码”假设被破坏而误判改动率。BOM/GBK 场景会直接卡死内层迭代。
- **建议**：移植层不要用 `gw_surgical_replace` 做大文件编辑，或前置把文件规整为 UTF-8 无 BOM + 统一 LF；并把
  “换行重写”写进已知限制。

---

### P1-9 `hard_fork` 不校验祖先提交 → 静默空孤岛；lineage_id 同秒碰撞

- **位置**：`lib/engine.py:862-863`（`fork_commit = ancestor_commit or ...`；`new_lineage_id = f"LIN-{new_family_id}-FORK-{int(time.time()) % 10000:04d}"`）；
  `lib/sandbox.py:607-615`（快照目录不存在时静默创建空 `src/local_tests/legacy_out`）
- **症状**：
  1. 传入不存在的 `ancestorCommit` 时，`checkout_clean_island` 只是建空目录，返回 `status: OK`，孤岛里没有
     `src/main.py`；后续 `gw_evaluate_slot` 才报“找不到入口脚本”，节点代码已丢。
  2. lineage_id 只取**秒级时间戳后 4 位**；同一秒内两次 hard_fork（两次调用间隔 <1s 很正常）产生相同 id，后一次
     覆盖前一次的血统记录；本次战役实测两次分叉都得到 `LIN-FAM-02-FORK-7450`。
- **复现**：

```powershell
python -B plugins/dsh-greatwall-agent/docs/audit/probe_campaign.py
# step 16: gw_lineage_control/hard_fork(bad ancestor) -> status OK, island_src_files=[]
# step 17: gw_lineage_control/hard_fork          -> new_lineage_id 与 step 16 相同
```

- **期望 vs 实际**：期望未知 commit 立即报错且不破坏现有槽位；lineage_id 全局唯一。实际 `OK` + 空孤岛；ID 冲突。
- **证据**：`audit/campaign_result.json`（step 14/16 `hard_fork(bad ancestor)` 与 step 15/17 的 `new_lineage_id`）、
  `audit/campaign_run.log`。
- **对 DSH 移植的影响**：无人值守下“分叉到祖先”是损失最小化的关键操作；现状会把节点工作区清空且以为成功。血统碰撞会
  让 `steps_invested`/`last_reflected_step` 串线，60 步内省室计数失真。
- **建议**：移植层在 hard_fork 前校验 `ancestorCommit` 在 `.kernel_vault/snapshots/` 下存在；lineage 冲突以
  `steps_invested`/`head_commit` 校验。

---

### P1-10 `mcp_config.json` / `hooks.json` 硬编码本机绝对路径，不可随包分发

- **位置**：`mcp_config.json:4-10`、`hooks.json:8-10`
- **症状**：原插件清单把 Python 解释器与插件安装目录写死为本机路径：

```json
"command": "C:\\Users\\wangy\\AppData\\Local\\Programs\\Python\\Python314\\python.exe",
"args": ["C:\\Users\\wangy\\.gemini\\config\\plugins\\greatwall-agent\\bin\\gw_mcp_server.py"]
```

  `hooks.json` 的 `command` 同样写死这两个路径，且 `matcher` 是 Antigravity 的工具名
  `read_file|write_file|edit_file|run_command`。
- **复现**：直接读取上述文件（`plugins/greatwall-agent/mcp_config.json`、`hooks.json`）。
- **期望 vs 实际**：期望安装后按实际路径生成/变量化；实际只能在这台机器上工作。
- **证据**：文件原文（两处 4-10 / 8-10 行）。
- **对 DSH 移植的影响**：**移植包不得复制这两个清单**；DSH 侧必须由 `package.json`/cordis patch 自己生成 MCP
  注册（当前 DSH 实测桥工作正常，说明移植层已重做注册，但若未来“整包复制”会立刻坏）。同时 `hooks.json` 的
  matcher 也解释了为什么 DSH 必须重写 gate（P1-7）。
- **建议**：在移植包 README/脚本中明确“mcp_config.json 与 hooks.json 不随包生效，仅作 Antigravity 参考”；
  由安装脚本用当前解释器/绝对安装路径渲染。

---

## 3. P2（风险与脆弱性）

> 以下均给出文件:line 与证据；静态项标注“静态证据”，动态项给出 `evidence id`。

### P2-1 缺省 `workspaceRoot` 时回退到服务端 cwd，并就地创建完整运行工作区

- **位置**：`bin/gw_mcp_server.py:330-331`（`workspace_root = args.get("workspaceRoot") or os.getcwd()`；
  每个工具调用都会 `GreatWallEngine(workspace_root)`）
- **证据**：`audit/mcp_conformance_result.json` → “缺省 workspaceRoot 时回退到服务端 cwd，并在那里创建完整运行工作区”
  （PASS，`created: {vault:true, secret:true, shared_readonly:true, worktrees:true}`）。
  另一次真实污染：畸形 `params:[]` 帧触发 `handle_tool_call("", {})`，在 `docs/audit/` 下生成了
  `.kernel_vault/hmac_secret.key`、`shared_readonly/archive/...`、`worktrees/`、`.trash_graveyard/`——
  已记录于 `audit/accidental_workspace_evidence.json` 并从仓库删除。
- **影响/建议**：任何参数不全的 `tools/call` 都会在 MCP 服务进程 cwd（DSH 上可能是用户项目目录）落地一个
  运行工作区。移植层应在包装层强制 `workspaceRoot` 必填并校验。

### P2-2 MCP 帧细节：Windows 上输出 CRLF、协议版本写死、无 `ping`/批量支持

- **位置**：`bin/gw_mcp_server.py:467`（写 `\n`）、`474-475`（`reconfigure` 保留 newline 翻译 → 实际 `\r\n`）、
  `491-504`（固定返回 `protocolVersion: "2024-11-05"`）
- **证据**：`audit/mcp_conformance_result.json` 中 `params as array` 帧的 `response_raw` 以 `\r\n` 结束；
  `initialize` 无论客户端请求什么版本都回 `2024-11-05`；`ping` 未实现（返回 `-32601`）。
- **影响**：严格的逐字节 MCP 客户端可能不接受 CRLF；协议版本协商不完整。本次 DSH 桥未受影响。
- **建议**：移植层 stdout 包装可 `strip()` 掉 `\r`；文档写明仅支持 `2024-11-05`。

### P2-3 HMAC 覆盖字段不全 + 密钥生成无锁竞态

- **位置**：`lib/evaluator.py:389-405`（签名只覆盖 `node_id|commit_hash|run_nonce|frozen|live`；
  `verify_receipt_signature` 只比这 5 个）、`lib/evaluator.py:384-387`（`_ensure_secret` 先 `exists()` 再写，无文件锁）
- **证据**：`audit/security_result.json` D1 —— 篡改 `triage_tier`、`case_scores`、`niche_hard_cases_score`、
  `isomorphic_perturbation_gap` 后 `original_verifies=true, tampered_still_verifies=true`。
- **影响**：收据未签字段可被任意改写（尤其 `triage_tier` 直接影响入榜与提分判定）。
- **建议**：移植层不要信任未签字段；多进程场景避免首次并发初始化（先由 `gw_init_campaign` 生成密钥）。

### P2-4 `.kernel_vault/evaluator_suite/evaluate_runner.py` 是隐式信任执行点

- **位置**：`lib/evaluator.py:484-500`（若该文件存在，引擎用 `sys.executable <runner> --candidate-script ...` 执行它）
- **证据**：静态证据（代码行）；全仓库无任何创建该文件的代码（`grep evaluate_runner` 仅命中 evaluator 两处）。
- **影响**：结合 P1-2（被测代码可写 vault），一次评测可植入该 runner，下一次评测即执行攻击者代码且带引擎权限。
  目前只是潜在链，未实测（见 §8 待复核）。
- **建议**：移植层启动时校验该文件不存在或哈希固定。

### P2-5 跨进程锁：15s 超时、不可重入、临界区可能超过超时

- **位置**：`lib/sandbox.py:43`（默认 15s）、`53-71`（非阻塞轮询）；`lib/engine.py:611-717`（`submit_legacy` 在
  持锁期间跑 BarrierProof 15s + 每个原语单测 10s）
- **证据**：`audit/runtime_result.json` L2 —— 同进程再次加锁 `TimeoutError after 0.42s`（不可重入）；
  L1 —— 40 进程 ×4 次 RMW 恰好 160，**锁本身正确**。
- **影响**：多子代理并发时，后来者可能在 15s 后收到 `TimeoutError`（MCP 层表现为 `isError:true` 的 traceback），
  尤其发生在 `submit_legacy` 长临界区期间；若 DSH 在同一进程内用线程并发调用，会直接互锁超时。
- **建议**：移植层串行化工具调用或把超时调到 ≥ 300s；不要嵌套同一把锁。

### P2-6 `force_cleanup_directory`：依赖 `pwsh`、扫墓竞态、可能误关句柄

- **位置**：`lib/sandbox.py:215-226`（`subprocess.run(["pwsh", ...])` 强杀）、`269-274`（清空整个 `graveyard_dir`）、
  `158-173`（`_close_in_process_handles` 遍历 `gc.get_objects()` 关闭目标目录下所有 `IOBase`）
- **证据**：`audit/runtime_result.json` 未直接覆盖；静态证据见行号。
- **影响**：① 未装 PowerShell 7 的机器上强杀分支静默跳过（`except: pass`）；② 并发清理时可能删掉别的进程刚移入的
  tombstone；③ `_close_in_process_handles` 会关闭引擎自身仍在使用的文件句柄（若目标目录恰好包含日志/状态文件）。
- **建议**：移植层避免并发对同一工作区做清理；把 PowerShell 7 列为运行前提。

### P2-7 Job Object 绑定存在竞态（本次实测通过，但机制脆弱）

- **位置**：`lib/sandbox.py:480-490`（`Popen` 返回后才 `AssignProcessToJobObject`）
- **证据**：`audit/runtime_result.json` P1/P2 —— 超时 2s 后孙进程未存活、200MB 分配在 64MB 限制下 `MemoryError`，
  说明**当前机器上**绑定成功；但子进程先运行后绑定，理论上可在此之前派生逃逸进程。
- **影响**：在低频/短命子进程上难以触发；长程/恶意代码可抢跑。
- **建议**：如要求强限额，需要 `CREATE_SUSPENDED` 方案（核心不可改，移植层可包一层）。

### P2-8 `wal.jsonl` 只写不重放，“崩溃自愈”宣称未实现

- **位置**：`lib/engine.py:56-64`（`_append_wal` 仅追加）、全仓库无读取 `wal.jsonl` 的代码
  （`grep wal_file|wal.jsonl|_append_wal` 仅命中定义与写入点）
- **证据**：静态证据（grep 结果与代码行）。
- **影响**：模块 docstring/架构文档所称“预写式事务日志崩溃自愈对齐”没有实现；崩溃后状态仍以 `state_graph.json`
  为准。属于宣传与实现不一致（见 P2-18）。
- **建议**：DSH 文档不要宣称 WAL 自愈；必要时移植层自己做状态备份。

### P2-9 `task_config.yaml` 实际内容是 JSON（伪 YAML）

- **位置**：`lib/engine.py:237-238`（`task_cfg_path.write_text(json.dumps(...))`，文件名固定为 `.yaml`）、
  `lib/evaluator.py:422-427`（`json.loads(task_cfg_path.read_text(...))`）
- **证据**：战役实测 `shared_readonly/task_config.yaml` 首字符为 `{`（`audit/campaign_result.json` step 1 的
  `task_config_path` 与文件内容可复核）。
- **影响**：链路内自洽；但任何按 YAML 语义编辑/生成的工具或人会把 A_data 清点写成 YAML，`json.loads` 失败被
  `except: pass` 吞掉 → 多模态完整性检查静默失效。
- **建议**：移植层不要在 `.yaml` 上做 YAML 解析；文档注明“实为 JSON”。

### P2-10 AST 审计三处局限：注释误杀、伪动态变量、放行 `subprocess/os.system`

- **位置**：`lib/evaluator.py:159-172`（黑名单裸正则扫全文）、`305-333`（`_verify_variable_is_dynamic`，
  `331-332` 行 `constant_assignments > 1` 即判动态）、`69-74`（禁 `ctypes/socket/eval`，**不含 `subprocess`/`os`**）
- **证据**：`audit/static_claims_result.json` K1（注释里出现 `LogisticRegression` → 整份代码被拒）、
  K2（`e = 2` 加死分支 `e = 3` → 判定为动态探索，`passed=true`）、K3（`import subprocess, os` + `os.system`
  → `passed=true`）。
- **影响**：误杀会让合法方案被拒；漏杀让“防作弊”名不副实（可 `subprocess` 读 vault/联网）。
- **建议**：移植层不要依赖这三项作为安全边界；拒绝理由里的“误杀”应允许人工豁免。

### P2-11 指标解析器兜底接受裸 JSON 行，且“最后一行获胜”

- **位置**：`lib/evaluator.py:868-884`
- **证据**：`audit/static_claims_result.json` K4（`"some log\n{\"frozen_score\": 5.0}\n"` → 解析成功；
  两行 marker 时取最后一行）；`audit/security_result.json` C2（atexit 伪造行覆盖真实分数）。
- **影响**：P1-1 的自证通道之一；解析器无来源校验。
- **建议**：移植层对被评代码 stdout 做白名单（只认引擎自己的 marker），或在包装层重新计算分数。

### P2-12 微创替换只校验新代码块第一个 AST 节点，且会静默丢装饰器

- **位置**：`lib/sandbox.py:697-706`（只检查 `new_tree.body[0]` 的名称）、`746-756`（按 `lineno/end_lineno`
  整段替换，装饰器行号被合并进 start_line 后随旧代码一起丢弃）
- **证据**：`audit/runtime_result.json` S4（`def solve` 后追加 `import os; os.system(...)` 仍 `result=true`，
  语句被原样插入）、S5（`@functools.lru_cache` 被静默删除，工具报成功）。
- **影响**：节点可以通过“替换代码块”往文件里塞任意顶层语句（配合 P1-2 变成执行通道）；带装饰器的函数被替换后
  性能/缓存语义改变却无警告。
- **建议**：移植层要求新代码块只包含单个 def/class；替换装饰器函数时显式提示。

### P2-13 `compile_final_delivery` 允许空正文通过“防吹牛”门禁

- **位置**：`lib/engine.py:983-994`（只检查占位符，未校验正文长度/必填章节）
- **证据**：`audit/security_result.json` G1（`executiveSummaryMd=""` → `status: OK`，`01_executive_report.md`
  仅 371 字节，正文为空）。
- **影响**：“终局防吹牛”只防模板占位符，不防空报告；DSH 交付物可能是一份没有任何方法论的报告。
- **建议**：移植层要求非空正文与最小长度，否则拒绝交付。

### P2-14 记录 ID 碰撞与墓志铭阈值不一致

- **位置**：`lib/archive.py:540`（`REC-{int(time.time()*1000)%100000:05d}`）、`lib/engine.py:772`（同款）
  `lib/archive.py:372-376`（错误信息“至少 15 字”，docstring 说 <=300，代码在 >500 时才截断到 300）
- **证据**：静态证据（代码行）；未构造真实碰撞（见 §8）。
- **影响**：同一毫秒内两个节点可产生同名 `REC-xxxxx`，L2 点读会命中错记录；墓志铭规则自相矛盾。
- **建议**：移植层以 `node_id + timestamp` 作为主键查记录；不要依赖 `REC-` 唯一性。

### P2-15 未初始化即可分配槽位；`stepsConsumed` 未校验

- **位置**：`lib/engine.py:437-523`、`554-600`（无 `state["initialized"]` 检查，只有 `lock_opening_distillation`
  在 `283-284` 行检查）、`lib/engine.py:693`（`total_steps_executed += steps_consumed`，`steps_consumed` 来自 MCP 参数，可为负）
- **证据**：`audit/uninitialized_allocate.log` —— `state_initialized = False`，`allocate_status = OK`，
  `base_commit = GENESIS_S0`，孤岛只有 `scoped_brief.md`。
- **影响**：DSH 上模型可跳过 Phase 0 直接开槽，在空基线上评测，污染 state/排行榜。
- **建议**：移植层在包装层强制“init → lock → allocate”顺序；`stepsConsumed` 限定 0..step_budget。

### P2-16 路径牢笼只用于一个参数，`validate_read` 是死代码

- **位置**：`lib/sandbox.py:97-151`（`SandboxPathJail`）、`lib/engine.py:539-540`（只有 `gw_surgical_replace` 的
  `relScriptPath` 走 `validate_write`）；全库 0 个 `validate_read` 调用点（`grep validate_read` 仅定义与测试）
- **证据**：`audit/runtime_result.json` J1/J2（越界写与 junction 逃逸被正确拦截，说明实现本身可用；但只覆盖一处）。
- **影响**：`gw_archive_query`（P1-3）、`gw_submit_legacy` 的反例脚本（P1-5）等都不经过 jail；`validate_read`
  的跨血统隐私规则在生产路径上从未执行。
- **建议**：移植层对每个带路径参数的 MCP 工具统一做 realpath 包含性校验。

### P2-17 路径字符串注入点（f-string 拼 Python 代码）

- **位置**：`lib/evaluator.py:638-639`（`driver_code` 里 `r"{str(script_a_path.resolve())}"`）、
  `lib/archive.py:706-714`（`r'{str(py_file.resolve())}'`）
- **证据**：静态证据（代码行）。Windows 用户名含 `'` 或路径含 `"` 时会生成非法/可注入代码。
- **影响**：低概率但会造成“脚本路径存在却评测失败”的不可解释错误；恶意路径可注入代码。
- **建议**：移植层对路径做 `repr()` 校验或改用 `subprocess` argv 传参。

### P2-18 文档/注释宣称与实现不一致（汇总）

| 宣称 | 实现事实 | 位置 |
|---|---|---|
| 「清洁室物理隔离 / 特权保险箱」 | 无 OS 级隔离，可读写任意路径，可读 HMAC 密钥 | P1-2 |
| 「HMAC 防伪成绩单 / 防吹牛」 | 分数来自被测代码自报；签名只覆盖 5 字段 | P1-1、P2-3 |
| 「预写式事务日志崩溃自愈」 | `wal.jsonl` 只写不重放 | P2-8 |
| 「原语 AST 审计 + 沙箱单测准入」 | 无 AST 安全审计，直接执行节点代码 | P1-6 |
| 「BarrierProof 沙箱反例脚本证实」 | 只看 exit=0，空脚本即认证，路径可越界 | P1-5 |
| 「60 步深挖锁 / 内省室」 | `submit_reflection` 在 0 步即可提交并重置 `last_reflected_step`；可把 60 步门禁推后 | P2-19 |

### P2-19 60 步内省室契约可被提前提交“稀释”

- **位置**：`lib/engine.py:915-965`（`submit_reflection` 不校验 `steps_invested >= 60`，直接把
  `last_reflected_step = step_now`）、`lib/engine.py:707-710`（触发条件 `last_reflected_step + 60 <= steps_invested`）
- **证据**：`audit/campaign_result.json` step 20 —— 新分叉血统 `steps_invested=0` 时提交内省，
  返回 `reflection_id: REFLECT-LIN-FAM-02-FORK-7450-0`、`last_reflected_step: 0`。
- **影响**：在 59 步提交一次即可把“满 60 步必须内省”推迟到 119 步，反复操作可无限规避；属于机制可被策略性玩弄。
- **建议**：移植层额外强制“仅当 `steps_invested>=60` 且距上次内省 ≥60 步才接受提交”。

---

## 4. MCP / JSON-RPC 一致性检查总表

来源：`audit/mcp_conformance_result.json`（服务器 `bin/gw_mcp_server.py`，Python 3.14.7）。

| # | 检查项 | 结果 | 说明 |
|---|---|---|---|
| 1 | `initialize` 返回 MCP result（protocolVersion/serverInfo/capabilities） | PASS | 固定 `2024-11-05`，延迟 ~95ms |
| 2 | `notifications/initialized` 无响应 | PASS | 静默 |
| 3 | 未知 notification 无响应（不刷 -32601） | PASS | 静默 |
| 4 | `tools/list` 恰好 9 个工具 | PASS | 与 `TOOLS_SCHEMA` 一致 |
| 5 | 每个 `inputSchema` 为 object 且 required 含 `workspaceRoot` | PASS | |
| 6 | `tools/call` happy path（archive get_l0_index） | PASS | `status:OK` |
| 7 | UTF-8 参数往返（中文+emoji） | PASS | 落盘文件内容一致 |
| 8 | 非法 JSON → `-32700` 且服务存活 | PASS | `id:null` |
| 9 | 未知方法 → `-32601` 且 id 回显 | PASS | |
| 10 | 字符串 id 原样回显 | PASS | |
| 11 | 缺必填参数 → JSON-RPC result + `isError:true`（不崩） | PASS | 但 content 里带整段 traceback |
| 12 | 未知工具名 → `isError:true` | PASS | |
| 13 | **业务 status=ERROR 映射为 `isError:true`** | **FAIL** | 见 P0-2 |
| 14 | stdout 只含 JSON-RPC 帧 | PASS | 11 帧全部可解析 |
| 15 | 正常路径 stderr 静默 | PASS | |
| 16 | 缺省 `workspaceRoot` 回退 cwd 并创建工作区 | **风险** | 见 P2-1 |
| 17 | stdin EOF 后干净退出（exit 0） | PASS | |
| 18 | **`[batch]` 数组帧** | **FAIL** | 服务退出 1（P0-1） |
| 19 | **`null` 帧** | **FAIL** | 服务退出 1 |
| 20 | **数字帧** | **FAIL** | 服务退出 1 |
| 21 | **字符串帧** | **FAIL** | 服务退出 1 |
| 22 | `params` 为数组（tools/call） | PASS（侥幸） | 不崩，但工具名为空 → `isError:true`，且**在服务端 cwd 创建了工作区**（实际发生过） |
| 23 | 缺 `method` 的请求 | PASS | `-32601` |
| 24 | LSP `Content-Length` 分帧 | INFO | 不支持（MCP stdio 规定换行分帧，合规）；会先回 `-32700` |
| 25 | 响应帧行尾 | INFO | Windows 下为 `\r\n`（P2-2） |

**结论**：协议“正常路径”基本合规；**异常路径 4/4 崩溃**，**业务错误语义全丢**。移植层必须加上 P0-1/P0-2 两层防护，
否则不能宣称“MCP 一致”。

---

## 5. 九工具战役 smoke test 全链路

来源：`audit/campaign_result.json`、`audit/campaign_run.log`、`audit/campaign_probe_console.log`。
工作区：`%TEMP%\gw_audit_campaign_bmuy1z1d\workspace`（仓库外）；全程 JSON-RPC 驱动（非直接 import）。

| # | 步骤 | 用时(s) | `isError` | 业务 status | 备注 |
|---|---|---|---|---|---|
| 1 | `gw_init_campaign` | 0.02 | false | OK | EDA 扫描 2 个模态文件（train.csv/meta.json） |
| 2 | `gw_lock_distillation` | 0.15 | false | OK | 2 候选竞技，s0=`76231cce2e64377c`，`anchor_s0_score=20277.0`（注意 P1-1） |
| 3 | `gw_allocate_slot` | 0.01 | false | OK | `slot_01_node-001`，base_commit=s0 |
| 4 | `gw_surgical_replace` | 0.01 | false | OK | 原位替换 `solve`，diff.patch 176 字节 |
| 5 | `gw_evaluate_slot`（伪称消融变量 `scale`） | 0.01 | **false** | **REJECTED_BY_AST_AUDITOR** | 门禁工作，但按 P0-2 被报成功 |
| 6 | `gw_evaluate_slot`（干净） | 0.06 | false | （收据） | `PARETO_PROMOTE`，frozen=40554.0，`structural_diff_ratio=0.0612` |
| 7 | `gw_submit_legacy` | 0.07 | false | OK | 入库原语 `sum_squares.py`、claim、record；rank=1；steps=20 |
| 8 | `gw_archive_query/get_l0_index` | 0.00 | false | OK | 837 字符索引 |
| 9 | `gw_archive_query/get_l2_item(primitive)` | 0.00 | false | — | 返回 `type:primitive` + 源码 |
| 10 | `gw_archive_query/get_l2_item(record)` | 0.00 | false | — | 返回 `type:record_blacklist` |
| 11 | `gw_archive_query/get_campaign_status` | 0.00 | false | OK | `STAGE_1_DIVERGENT_EXPLORATION`，steps=20 |
| 12 | `gw_compile_delivery`（正文含 TODO） | 0.00 | **false** | **DELIVERY_BLOCKED_PLACEHOLDERS** | 门禁工作，但被报成功 |
| 13 | `gw_compile_delivery`（干净） | 0.01 | false | OK | 五件套全部生成 |
| 14 | `gw_allocate_slot#2` | 0.01 | false | OK | `slot_01_node-002`（编号复用，非缺陷） |
| 15 | `gw_lineage_control/soft_flush` | 0.03 | false | OK | 回滚至 s0，失败记录置顶 |
| 16 | `gw_lineage_control/hard_fork`（**非法祖先**） | 0.02 | false | **OK**（应为错误） | 孤岛 `src/` 为空（P1-9） |
| 17 | `gw_lineage_control/hard_fork`（合法 s0） | 0.03 | false | OK | `new_lineage_id` 与 step 16 相同（P1-9 碰撞） |
| 18 | `gw_lineage_control/differential_test` | 0.05 | false | OK | 3 个压力用例，发现 2 处分歧（机制工作） |
| 19 | `gw_lineage_control/deprecate_errata` | 0.00 | false | OK | 无历史 case_scores，重算 0 条 |
| 20 | `gw_lineage_control/submit_reflection` | 0.01 | false | OK | 0 步血统即内省（P2-19） |

**结论**：九工具**功能链路全部打通**（这是移植可行性的正面证据），但存在 3 个“业务拒绝报成功”（#5/#12 + P0-2）、
1 个“非法输入报成功”（#16）、1 个“契约可绕过”（#20）。

---

## 6. hook_gate.py 决策矩阵（25 例）

来源：`audit/hook_gate_result.json`。`intended` 指模块 docstring 承诺的语义。

| # | 场景 | 期望 | 实际 | 判定 |
|---|---|---|---|---|
| H01 | `read_file` 读 `.kernel_vault`（Antigravity 形状） | deny | deny | ✅ |
| H02 | `write_file` 写 `shared_readonly` | deny | deny | ✅ |
| H03 | `run_command` 重定向写 `shared_readonly` | deny | deny | ✅ |
| H04 | `run_command` `../slot_` | deny | deny | ✅ |
| H05 | 一条命令引用两个 `worktrees/slot_` | deny | deny | ✅ |
| H06 | 只读 `shared_readonly` | allow | allow | ✅ |
| **H07** | **DSH `read` + `file_path` 指向 `.kernel_vault`** | deny | **allow** | ❌ 失效 |
| **H08** | **DSH `write` + `file_path` 指向 `shared_readonly`** | deny | **allow** | ❌ 失效 |
| **H09** | **DSH `edit` + `file_path` 指向 `hmac_secret.key`** | deny | **allow** | ❌ 失效 |
| **H10** | **DSH `pwsh` + `command` 重定向写 `shared_readonly`** | deny | **allow** | ❌ 失效 |
| **H11** | `.KERNEL_VAULT` 大写 | deny | **allow** | ❌ Windows 大小写 |
| **H12** | `SHARED_READONLY` 大写 | deny | **allow** | ❌ |
| **H13** | `../SLOT_` 大写 | deny | **allow** | ❌ |
| **H14** | `Copy-Item` 写 `shared_readonly` | deny | **allow** | ❌ 黑名单缺项 |
| **H15** | `python -c open('shared_readonly/...','w')` | deny | **allow** | ❌ 黑名单缺项 |
| **H16** | `New-Item` 在 `shared_readonly` 建文件 | deny | **allow** | ❌ |
| **H17** | 绝对路径读隔壁槽位 | deny | **allow** | ❌ 只认 `../slot_` |
| **H18** | `slot_02_node-002/src/main.py`（无 `worktrees/` 前缀） | deny | **allow** | ❌ |
| **H19** | 环境变量拼接 `.kernel_vault`（无字面量） | deny | **allow** | ❌ |
| **H20** | 通配符 `.kernel_*/...` | deny | **allow** | ❌ |
| H21 | 空 stdin | 未定义 | allow | ⚠️ fail-open |
| H22 | 非法 JSON | 未定义 | allow | ⚠️ fail-open |
| H23 | 顶层 JSON 数组 | 未定义 | allow | ⚠️ fail-open |
| H24 | 缺 `toolCall` | 未定义 | allow | ⚠️ fail-open |
| H25 | `read_file` 普通文件 | allow | allow | ✅ |

**结论**：Antigravity 原形状下核心三条规则有效；**DSH 形状下等于不存在**；另有 9 条同类绕过。移植包必须自研
DSH 原生 gate（当前 `lib/gate.js` 若只是复刻子串匹配，需要按上表补 fail-closed 与 realpath 校验）。

---

## 7. 对 DSH 移植的具体结论与「不可照搬清单」

**可以照搬（逐字节）**：`lib/` 与 `bin/gw_mcp_server.py`（这是移植前提），但必须配合下列移植层防护。

**不可直接照搬**：
1. `bin/hook_gate.py` —— 只适配 Antigravity 工具协议（P1-7），DSH 必须重写为原生 gate。
2. `mcp_config.json` / `hooks.json` —— 硬编码本机绝对路径（P1-10）。
3. `plugin.json` 的 `suggestedPrompts`/描述中“清洁室/HMAC 防伪/防吹牛”的表述 —— 与 P1-1/P1-2/P1-5/P1-6 冲突（P2-18）。

**移植层必须补的防护（按优先级）**：
1. **MCP 守卫**：非对象帧 → `-32600` 并继续；业务 `status` → `isError` 映射（P0-1/P0-2）。
2. **档案检索白名单**：`itemId` 正则 + realpath 校验（P1-3）。
3. **提交护栏**：`gw_submit_legacy` 前先验 HMAC；`legacy_out/primitives/*.py` 先过 `ASTCodeInspector`（P1-4/P1-6）。
4. **真评测**：分数必须由引擎侧真值计算，禁止取 `evaluate()`/`solve()` 返回值（P1-1）。
5. **隔离承诺降级**：若要保留 `.kernel_vault` 保密性，需要 OS 级隔离，否则文档明确“逻辑隔离，非安全边界”（P1-2）。
6. **工具顺序约束**：init → lock → allocate → evaluate → submit；`hard_fork` 前校验祖先 commit（P1-9/P2-15）。
7. **文本编辑兜底**：替换前统一 UTF-8 无 BOM/LF，替换后校验未被触碰区域字节不变（P1-8）。
8. **并发**：工具调用串行化或把锁超时调到 ≥300s（P2-5）。

---

## 8. 未证实 / 待复核（不作为结论，仅登记）

| # | 事项 | 状态 |
|---|---|---|
| 1 | `state_graph.json` 损坏时 `load_state`（`engine.py:84` 裸 `json.loads`）的行为 | 未构造损坏文件实测；静态看会使所有工具返回 `isError:true` |
| 2 | POSIX/Linux 行为（Job Object 仅 Windows、`force_cleanup` 依赖 `pwsh`、CRLF 差异） | 未在 Linux 实测；DSH 跨平台移植需另测 |
| 3 | `evaluate_runner.py` 被植入后的链式利用 | P1-2 已证可写 vault，植入→下次执行链未实测 |
| 4 | DSH 桥是否会在真实运行中发送 JSON-RPC batch | 未观察到；但协议允许，且崩服务已复现（P0-1） |
| 5 | 同槽位并发 `gw_evaluate_slot` 与 `gw_submit_legacy` 的竞态 | 静态推断（`engine.py:566-598` 评测在锁外），未构造并发复现 |
| 6 | `force_cleanup_directory` 跨卷 `os.replace`（`sandbox.py:212`） | 未构造跨卷测试 |
| 7 | `REC-` 记录 ID 同毫秒碰撞 | 静态证据（`archive.py:540`），未构造真实碰撞 |
| 8 | `protocolVersion` 协商（客户端强制 2025-06-18） | 未测；服务器固定回 2024-11-05（P2-2） |
| 9 | `stepsConsumed` 传负数对阶段的操纵 | 静态证据（`engine.py:693`），未实测 |
| 10 | `IPv6`/防火墙相关（无） | — |

---

## 9. 证据文件索引

| 证据 | 内容 |
|---|---|
| `audit/e2e_run.log` | 自带 e2e 10/10 全量输出（`Ran 10 tests in 2.960s`） |
| `audit/mcp_conformance.log` / `audit/mcp_conformance_result.json` | 25 项 MCP 检查与原始响应 |
| `audit/crash_stderr_01..04_*.txt` | 4 个崩溃帧的完整 traceback（P0-1） |
| `audit/campaign_run.log` / `audit/campaign_result.json` / `audit/campaign_probe_console.log` | 九工具 20 步战役的每步请求/响应/耗时 |
| `audit/hook_gate_result.json` / `audit/hook_gate_probe.log` | 25 例 hook 决策（14 条 bypass 的完整 payload） |
| `audit/security_result.json` / `audit/security_probe.log` | A1/B1/C1/C2/D1/E1/E2/F1/G1 |
| `audit/submit_order_result.json` / `audit/submit_order_probe.log` | 先入库后验签（H1） |
| `audit/runtime_result.json` / `audit/runtime_probe.log` | S1/S1b/S2/S3（替换编码）、J1/J2（jail）、L1/L2（锁）、P1/P2/P3（Job Object/管道） |
| `audit/static_claims_result.json` / `audit/static_claims_probe.log` | K1~K5（黑名单误杀/伪动态/放行 subprocess/解析兜底） |
| `audit/uninitialized_allocate.log` | 未 init 即分配槽位（P2-15） |
| `audit/accidental_workspace_evidence.json` | P2-1 的真实污染记录（已在仓库外复测、仓库内已清理） |
| `audit/dsh_bridge_e2e.md` | DSH 真实 MCP 桥两次工具调用的请求/响应 |
| `audit/orig_tree_hashes_before.txt` | 原件 23 个文件的 SHA-256 基线（审计前后一致） |
| `audit/probe_*.py`、`audit/mcp_client.py` | 全部可复现探针（不含任何运行工作区） |

> 复现须知：所有探针以 `python -B` 运行；工作区均建在 `%TEMP%`；`docs/audit/` 下只保留脚本、日志、结构化结果，
> 不含 `.kernel_vault/`、`shared_readonly/`、`worktrees/`、`final_delivery/` 等运行目录（已清理并复核为空）。
