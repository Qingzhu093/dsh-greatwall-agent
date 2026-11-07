# Great Wall Agent V4.2 — Google Antigravity Plugin (`greatwall-agent`)

专为 **Google Antigravity** 打造的**长程无人值守 AI for Science 与算法竞赛攻关插件**。将《长城 Agent V4.2 无人值守架构与沙箱工程实战规范》的核心机制以**零第三方依赖、高内聚、无臃肿样板**的纯 Python 3 标准库实现落地。

---

## 核心特性与架构对齐

1. **Phase 0 开局先蒸馏引擎 (`gw_init_campaign` + `gw_lock_distillation`)**
   - 自动扫描 `shared_readonly/datasets_public/` 生成多模态数据资产清点表，锁死开局消歧结论（`task_config.yaml`），杜绝盘中盲目分裂 $A / \neg A$ 歧义分支；
   - 固化正交现代 SOTA 方法族、《反预训练熟悉度偏见黑名单》（防 2015 `ResNet` / 裸 `LogisticRegression`）与《调库 vs 造轮子边界清单》，并在沙箱实跑铸造**【零号强基线 $s_0$】**。
2. **无 `.git` 清洁室孤岛与 MLE-STAR 微创代码手术 (`gw_allocate_slot` + `gw_surgical_replace`)**
   - 导出给探索节点的孤岛目录 `worktrees/slot_xx_node_yy/` 内部 100% 不含 `.git` 元数据，并由 `SandboxPathJail` 路径牢笼与 `PreToolUse` 钩子阻止越界访问 `.kernel_vault` 或跨血统偷看；
   - 提供 AST 级 `gw_surgical_replace` 工具，冻结外围框架，仅原位热插拔替换锁定的瓶颈函数/类代码块 $c_t$，消除全量重写导致的 41.7% 语法崩溃。
3. **跨进程 HMAC 防伪评测与 AST 刑侦 (`gw_evaluate_slot`)**
   - 通过 Windows Job Object 绑定进程树连坐强杀（`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`）与物理内存硬封顶；
   - 自动执行 AST 安全逃逸检查、MLE-STAR 数据泄漏检查、计算图结构改动率对账（拦截 0% 结构改动的纯改常数微调）、声明变量动态性核对、四元组剥皮查新与同构置换扰动测试（抓捕背题号作弊），签发带一次性盐值 `run_nonce` 的 HMAC-SHA256 防伪成绩单。
4. **轻量级文件系统档案馆与五件套遗产协议 (`gw_submit_legacy` + `gw_archive_query`)**
   - 不依赖重型向量数据库（Zero Vector RAG），纯文件系统维护 `L0 全局索引 -> L1 节点专属启动简报 -> L2 按需点读`；
   - 利用 AST 自动提取 `archive/ledger/primitives/*.py` 的函数签名生成 `PRIMITIVES_API.md`（**调库不读码**），入库前强制在隔离沙箱实跑原语自带的 `def test_*():` 单元测试；
   - 内置防 `WinError 32` 五步墓碑原子移走与指数退避回收算法。
5. **终局防吹牛数字硬绑定与五件套交付 (`gw_compile_delivery`)**
   - 自动拦截 `TODO / TBD / Conclusions Here` 模板占位符，强制从 HMAC 签名收据硬绑定生成实验得分对比表，一键打包 `final_delivery/` 标准五件套。

---

## 目录结构

```text
greatwall-agent/
├── plugin.json                        # Antigravity 插件清单
├── mcp_config.json                    # Stdio MCP Server 配置
├── hooks.json                         # PreToolUse 清洁室边界守护钩子配置
├── assets/logo.svg                    # 插件图标
├── bin/
│   ├── gw_mcp_server.py               # JSON-RPC 2.0 Stdio MCP 服务端入口 (8 大核心工具)
│   └── hook_gate.py                   # 轻量零误伤 PreToolUse 安全门禁脚本
├── lib/
│   ├── __init__.py
│   ├── sandbox.py                     # 路径牢笼、Job Object 限额、五步墓碑回收与 AST 微创替换
│   ├── archive.py                     # L0/L1/L2 轻量档案馆、原语 AST 提取、五件套遗产验收与撤回树
│   ├── evaluator.py                   # AST 反作弊/防泄漏对账、四元组剥皮查新与跨进程 HMAC 评测
│   └── engine.py                      # 全周期状态机、WAL 预写日志、60步内省计数与终局交付编译
├── rules/
│   └── AGENTS.md                      # 常驻精简攻关准则
├── skills/
│   └── greatwall-campaign/SKILL.md    # 四阶段标准作业手册
├── agents/
│   ├── gw-distiller.md                # Phase 0 开局蒸馏子智能体
│   ├── gw-explorer.md                 # 清洁室孤岛探索节点子智能体
│   └── gw-auditor.md                  # 独立审计官与 60 步内省室导师子智能体
└── tests/
    └── test_plugin_e2e.py             # 全链路端到端自动化验收测试套件
```
