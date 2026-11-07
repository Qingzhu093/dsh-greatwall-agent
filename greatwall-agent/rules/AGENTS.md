# 长城 Agent V4.2 无人值守科研与竞赛攻关准则 (Great Wall Agent Rules)

当用户启动算法竞赛、数学建模或 AI for Science 长程无人值守攻关任务（或调用 `gw_*` 系列工具）时，严格遵循以下五条核心工程铁律：

## 一、开局前置消歧与先蒸馏铁律 (Phase 0 Opening Distillation)
1. **严禁盲目分裂 $A / \neg A$ 题面歧义分支**：
   - 遇到题面规则未明说的歧义，在 `Phase 0` 优先通过**数据集静态探针（EDA）**核实，或让用户在开局花 30 秒拍板锁定（无人批处理时单次调用低幻觉旗舰模型仲裁），锁入 `gw_init_campaign` 的 `resolvedAmbiguities` 中。绝不为题面歧义开启穷举分支浪费算力。
2. **未完成开局蒸馏与零号强基线 $s_0$ 前，禁止派发探索分支**：
   - 开局必须先检索近 3 年同类 SOTA 方案（破除动辄掏出 2015 年 `ResNet` 或 `LogisticRegression` 的预训练熟悉度偏见），调用 `gw_lock_distillation` 固化正交方法族、《调库 vs 造轮子边界清单》并实跑验分铸造**【零号强基线 $s_0$】**。后续一切探索分支必须与 $s_0$ 硬碰硬对比。

## 二、内层微创迭代与防重复造轮子铁律 (Targeted Block Refinement)
1. **外层消融定靶 + 内层代码块微创替换**：
   - 在清洁室孤岛（`worktrees/slot_*`）内改代码时，先通过消融定位单一瓶颈代码块 $c_t$，冻结外围数据加载与验证框架，**优先调用 `gw_surgical_replace` 仅原位替换目标函数/类**，禁止无故全量重写几百行脚本引发语法崩溃。
2. **调库不读码，严禁重复造基础轮子**：
   - 凡 `PRIMITIVES_API.md` 中已登记的档案馆原语函数或 `build_vs_buy_contract.json` 指定的基础库（如 `GroupKFold`、`cKDTree`），直接在代码中 `import` 复用，严禁手搓低效重复实现。

## 三、末期遗嘱交接与五件套遗产铁律 (Node Legacy Protocol)
1. **盘中禁止当甩手包工头**：
   - 探索节点在沙箱执行中途遇到报错必须自行根据 Traceback 修复，严禁在盘中层层派生子智能体。
2. **退场强制交齐五件套遗产包**：
   - 节点退出前必须在孤岛 `legacy_out/` 下留齐：`epitaph.md`（150 字具体失败/经验墓志铭，严禁无反例脚本支撑的全局悲观谣言）、`metrics_receipt.json`（由 `gw_evaluate_slot` 签发的 HMAC 签名收据）、`primitives/*.py`（可选，抽离出的可复用纯函数，必须自带 `def test_*():` 单元测试）、`anomalies_and_bounties.json`（可选）与 `last_will_proposals.json`（1~3 条下一步接力遗嘱），最后调用 `gw_submit_legacy` 验收入库并安全回收孤岛。

## 四、防伪查新、科研品味路由与终局防吹牛铁律
1. **底层数学算子剥皮查新**：
   - 严禁给微批处理、L1/L2 正则、常规剪枝或简单网格调参冠以花哨形容词冒充方法学创新（`NOVEL_METHODOLOGY`）。
2. **60 步原位内省室与终局数字硬绑定**：
   - 当 `gw_submit_legacy` 返回 `trigger_60_step_reflection_chamber: true` 时，立即按原位 3 轮内省室九大拷问题库审视当前谱系是否陷入路灯效应或超参微调陷阱。
   - 终局调用 `gw_compile_delivery` 生成 `final_delivery/` 时，所有实验得分对比表必须 100% 由内核从 HMAC 签名收据硬绑定生成，严禁手敲捏造数字或残留 `TODO / Conclusions Here` 占位符。
