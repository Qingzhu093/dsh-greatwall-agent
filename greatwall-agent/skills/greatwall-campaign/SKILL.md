---
name: greatwall-campaign
description: 长城 Agent V4.2 无人值守科研与竞赛全周期编排技能。当用户需要启动算法竞赛、数学建模或 AI for Science 长程自动探索、运行 Phase 0 开局知识蒸馏、调度无 .git 清洁室孤岛微创迭代、执行 60 步原位内省室或打包终局五件套交付信封时激活。触发词：长城 agent、无人值守攻关、开局蒸馏、清洁室沙箱、五件套遗产、跨分支拼图。
---

# 长城 Agent V4.2 无人值守攻关标准作业规程 (Great Wall Campaign Runbook)

本技能驱动 `greatwall-agent` MCP 服务器提供的 8 个原生工具，将长程无人值守攻关划分为 **4 个确定性阶段**。

---

## 阶段 0：开局前置消歧与先蒸馏引擎 (Phase 0: Pre-Flight & Opening Distillation)

### Step 0.1：三步前置消歧与工作区初始化 (`gw_init_campaign`)
1. **数据静态探针（EDA Grounding）**：将公开数据集放入 `<workspace>/shared_readonly/datasets_public/`，检查字段类型、缺失率与分组键，消除 70% 的伪歧义。
2. **锁定规则性歧义**：若有数据无法判断的规则歧义，让人类花 30 秒拍板（或调用低幻觉旗舰模型单次仲裁），**绝对禁止在盘中分裂 $A / \neg A$ 歧义分支**！
3. 调用 `gw_init_campaign` 初始化工作区目录树（`.kernel_vault/`、`shared_readonly/archive/`、`worktrees/`）。

### Step 0.2：开局知识蒸馏与铸造【零号强基线 $s_0$】(`gw_lock_distillation`)
1. 委派 `gw-distiller` 子智能体（或在主控直接调用 `search_web`）检索近 3 年同类任务 SOTA 方案。
2. 编写结构清晰、模块化分块的【零号强基线 $s_0$】代码（例如将特征工程拆为 `def extract_features(data):`、求解器拆为 `def solve(inputs):`、评测拆为 `def evaluate():`）。
3. 调用 `gw_lock_distillation` 传入：
   - `orthogonalFamilies`：2~4 个正交现代方法族（如 `FAM-01` 树模型与物理特征、`FAM-02` 深度学习表征、`FAM-03` 混合整数规划与启发式邻域搜索）；
   - `obsoleteBlacklist`：禁止把 2015 `ResNet`、裸 `LogisticRegression` 或三重未向量化循环当主力；
   - `mustReuseLibraries`：强制调库的基础设施清单；
   - `anchorBaselineCode`：零号强基线源码（内核将自动在沙箱实跑测定基准分 `anchor_s0_score`）。

---

## 阶段 1 & 2：清洁室孤岛并发深耕与微创代码手术 (Clean-Room Slot Loop)

### Step 1.1：分配无 `.git` 清洁室孤岛 (`gw_allocate_slot`)
- 调用 `gw_allocate_slot` 为指定 `familyId` 分配槽位，明确指明本轮锁定的单一微创手术代码块 `targetedCodeBlock`（如 `extract_features`）与可证伪假说 `hypothesis`。
- 内核将在 `worktrees/<slot_id>/` 下导出不含 `.git` 的纯净快照，并自动生成 `scoped_brief.md`（L1 启动简报，含 `PRIMITIVES_API` 可直接 `import` 的原语函数签名表与近期死胡同避坑表）。

### Step 1.2：MLE-STAR 式局部代码块微创替换 (`gw_surgical_replace`)
- 在孤岛内迭代时，**严禁全量重写整个 Python 文件**！
- 调用 `gw_surgical_replace` 传入 `slotId`、`targetBlockName` 与 `newBlockCode`，内核利用 AST 精准原位替换目标函数/类并自动验证全文件语法。

### Step 1.3：跨进程防作弊评测与四级分诊 (`gw_evaluate_slot`)
- 调用 `gw_evaluate_slot` 在 Windows Job Object 硬件限额与脱敏环境变量下运行跨进程隔离评测：
  - 自动执行 AST 安全扫描、MLE-STAR 数据泄漏扫描、计算图结构改动率对账（拦截只改数字 0% 结构改动的伪创新）、四元组剥皮查新与同构置换扰动测试（抓捕背题号作弊）；
  - 在 `legacy_out/metrics_receipt.json` 生成带 HMAC-SHA256 防伪签名的成绩单，并返回四级分诊结果：
    - `PARETO_PROMOTE`：总分超越 $s_0$，晋升为主干新基线并自动获 $+25$ 步续期奖励；
    - `NICHE_CHAMPION`：在极端困难算例上表现卓越，保留其偏科原语留待跨分支拼图；
    - `IN_PLACE_REPAIR`：存在运行时报错，保留孤岛目录给 3 步快速原地修补机会；
    - `DEAD_END_ARCHIVE`：性能退化或违规，提取墓志铭归档黑名单。

### Step 1.4：五件套遗产验收入库与五步墓碑回收 (`gw_submit_legacy`)
- 节点退场前，在 `<island_path>/legacy_out/` 下写入：
  1. `epitaph.md`：$\le 150$ 字死胡同避坑或核心实验结论总结；
  2. `metrics_receipt.json`：已由 `gw_evaluate_slot` 自动生成；
  3. `primitives/<name>.py`（可选但强烈推荐）：将提分的独立纯函数抽离出来，必须包含类型注解、Docstring 以及 `def test_<name>():` 单元测试函数；
  4. `anomalies_and_bounties.json`（可选）：反常实验现象与悬赏；
  5. `last_will_proposals.json`：1~3 条下一步接力遗嘱提案（含 `action_type` 与 `falsifiable_hypothesis`）。
- 调用 `gw_submit_legacy`：内核自动在沙箱实跑 `primitives/*.py` 的单元测试，通过后正式入库 `archive/ledger/primitives/` 并刷新 `PRIMITIVES_API.md`，最后用五步墓碑算法（防 `WinError 32`）瞬间回收孤岛目录。

---

## 阶段 3：60 步原位内省室与品味校准 (Reflection Chamber & Taste Calibration)

当 `gw_submit_legacy` 返回 `trigger_60_step_reflection_chamber: true`（或全局陷入平台期）时：
1. 暂停常规 `EXTEND` 派发，切换至高品味审查视角（或唤醒 `gw-auditor`），按**原位 3 轮内省室九大拷问**对当前谱系进行冷酷解剖：
   - **第 1 轮（扒掉虚假繁荣）**：对照《正反品味锚点表》，检查是否掉进了“定性画图自嗨”、“静态边角料路灯效应”或“超参网格微调”三大摸鱼陷阱；
   - **第 2 轮（解剖最差算例）**：找出错得最离谱的 3 个算例，判断底层假设是否破裂，并调用 `gw_archive_query` 查看其他方法族是否已入库可互补的原语函数；
   - **第 3 轮（做减法与签军令状）**：删掉无边际贡献的冗余代码，锁定未来 20 步唯一攻克的代码块与证伪阈值（若证伪则提交《结构障碍证明》体面结题）。

---

## 阶段 4：四步跨分支结构拼图与终局五件套交付 (`gw_compile_delivery`)

1. **跨分支结构拼图（Structural Synthesis）**：
   - 调用 `gw_archive_query(action="get_l0_index")` 查阅 `PRIMITIVES_API.md` 中各方法族沉淀的优质原语；
   - 分配拼图槽位（`action_type: GRAFT`），在主干最优方案中直接 `from archive.ledger.primitives.xxx import yyy` 嫁接互补算子，实跑消融验证净收益。
2. **编译终局五件套交付信封 (`gw_compile_delivery`)**：
   - 调用 `gw_compile_delivery` 传入 `executiveSummaryMd`（严禁包含 `TODO / TBD / Conclusions Here` 占位符）；
   - 内核自动从 HMAC 签名收据硬绑定渲染全套实验得分对比表，在 `<workspace>/final_delivery/` 下生成标准五件套（报告、纯净源码与原语库、证据总账本、PowerShell 一键复现脚本、适用边界与死胡同避坑指南）。
