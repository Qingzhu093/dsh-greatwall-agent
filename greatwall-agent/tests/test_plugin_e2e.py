#!/usr/bin/env python3
"""
End-to-End & Adversarial Verification Suite for Great Wall Agent V4.2 Antigravity Plugin.
逐章逐项对照《15_长城Agent_V4无人值守架构与沙箱工程实战规范.md》(1~8 章) 执行真机严苛验收：
1. Phase 0 静态数据探针 (EDA Probe) + M 候选基线实跑排序择优固化 s_0 (§1.3 & §2.3)
2. 顶层函数与缩进类内方法 (`ClassName.method`) 的 AST 微创热插拔替换 + 自动生成 `diff.patch` (§2.2 & §5.3)
3. AST 法医级静态审计：拦截逃逸调用、过时模型黑名单、手搓基础轮子、遗漏多模态文件 (A_data)、静态写死伪消融变量与三大偷懒陷阱 (§2.3, §4.2, §5.6, §7.6.2)
4. PreToolUse Hook 门禁：拦截偷看 `.kernel_vault`、文件/终端重定向篡改 `shared_readonly` 与跨槽位偷看 (`../slot_`) (§5.2)
5. 五件套遗产包入库、原语沙箱单测、`PRIMITIVES_API.md` 零函数体提取、防同血统自引刷分与跨血统有效引用计数、错误结论依赖树撤回 (§3.2 & §3.3)
6. 60 步导师深挖承诺锁、死路反例脚本 (`BarrierProof`) 沙箱验证豁免与封禁、60 步原位 3 轮内省室契约持久化 (§7.1 & §7.6)
7. 原地软清栈 (`Soft Flush`) 回滚置顶警告 + 连续 3 次同因失败自动打补丁 (`Meta-Pattern Auto-Patch`) (§6.2.2 & §7.6.4)
8. 跨分支无标签极端算例差分互测 (`Differential Testing`) + 评测集错题热勘误与历史分数追溯平反 (`Retroactive Errata`) (§7.3.2 & §7.4)
9. 64 位 Windows Job Object 进程树强杀与内存统计 + 多线程/多进程并发文件锁 (`InterProcessFileLock`) 压力测试 (§5.4 & §6.3)
10. MCP Stdio JSON-RPC 9 大工具全链路协议通信与终局防吹牛五件套交付信封 (`final_delivery/`) 校验 (§8.3)
"""

from __future__ import annotations

import concurrent.futures
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from lib.archive import LightweightArchive
from lib.engine import GreatWallEngine
from lib.evaluator import ASTCodeInspector, IsolatedEvaluator
from lib.sandbox import CleanRoomSandbox, InterProcessFileLock, SandboxPathJail, force_cleanup_directory, run_bounded_subprocess


class TestGreatWallPluginV42SpecAlignment(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="gw_v42_test_"))

    def tearDown(self) -> None:
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_phase0_eda_probe_and_m_candidate_s0_tournament(self) -> None:
        """测试 §1.3 & §2.3：开局确定性 EDA 数据探针 + M 候选基线竞技选优锁定 s_0"""
        engine = GreatWallEngine(self.tmp_dir)
        ds_dir = self.tmp_dir / "shared_readonly" / "datasets_public"
        ds_dir.mkdir(parents=True, exist_ok=True)
        (ds_dir / "train.csv").write_text("id,feat_a,feat_b,target\n1,10.5,,1\n2,20.0,3.1,0\n3,,4.2,1\n", encoding="utf-8")
        (ds_dir / "meta.json").write_text(json.dumps([{"mol_id": "M1", "atoms": 12}, {"mol_id": "M2", "atoms": 18}]), encoding="utf-8")

        init_res = engine.init_campaign(
            task_id="MOL_PRED_2026",
            task_description="多模态分子性质预测",
            domain_type="BIO_CHEM",
            primary_metric="score",
            higher_is_better=True,
        )
        self.assertEqual(init_res["status"], "OK")
        eda = init_res["eda_probe_report"]
        self.assertEqual(eda["total_files"], 2)
        csv_mod = next(m for m in eda["modalities"] if m["file"] == "train.csv")
        self.assertEqual(csv_mod["num_rows"], 3)
        self.assertEqual(csv_mod["num_columns"], 4)
        self.assertAlmostEqual(csv_mod["missing_rates"]["feat_a"], 0.3333, places=3)

        # 传入 M=2 个候选基线：CAND_WEAK (得分 60.0) vs CAND_STRONG (得分 88.5)，验证自动选优锁定 88.5 为 s_0
        lock_res = engine.lock_opening_distillation(
            orthogonal_families=[
                {"family_id": "FAM-GNN", "family_name": "Equivariant GNN"},
                {"family_id": "FAM-GBDT", "family_name": "Modern GBDT + Graph Descriptors"},
            ],
            candidate_baselines=[
                {"name": "CAND_WEAK", "code": "def evaluate():\n    return {'frozen_score': 60.0, 'live_score': 59.0}\n"},
                {"name": "CAND_STRONG", "code": "def evaluate():\n    return {'frozen_score': 88.5, 'live_score': 87.0}\n"},
            ],
        )
        self.assertEqual(lock_res["status"], "OK")
        self.assertAlmostEqual(lock_res["anchor_s0_score"], 88.5)
        self.assertEqual(len(lock_res["candidate_tournament_log"]), 2)
        self.assertIn("88.5", (self.tmp_dir / "shared_readonly" / "distilled" / "anchor_baseline.py").read_text(encoding="utf-8"))

    def test_02_surgical_replace_top_func_and_indented_class_method(self) -> None:
        """测试 §2.2 & §5.3：顶层函数与缩进类方法 (`Solver.step` 及单方法名) 的 AST 微创替换与缩进自动对齐"""
        script = self.tmp_dir / "solver_app.py"
        script.write_text(
            "def preprocess(x):\n"
            "    return [v + 1 for v in x]\n\n"
            "class Solver:\n"
            "    def __init__(self, scale: float = 1.0):\n"
            "        self.scale = scale\n\n"
            "    def compute_step(self, vals):\n"
            "        return sum(vals) * self.scale\n\n"
            "if __name__ == '__main__':\n"
            "    s = Solver(2.0)\n"
            "    print(s.compute_step(preprocess([1, 2, 3])))\n",
            encoding="utf-8",
        )

        # 1. 传入零缩进的类方法代码，测试自动缩进对齐替换 `Solver.compute_step`
        new_method = (
            "def compute_step(self, vals):\n"
            "    filtered = [v for v in vals if v > 0]\n"
            "    return sum(v * v for v in filtered) * self.scale\n"
        )
        ok, msg = CleanRoomSandbox.surgical_replace_block(script, "Solver.compute_step", new_method)
        self.assertTrue(ok, msg)

        # 2. 不带类名直接用唯一方法名 `compute_step` 再次微创替换
        new_method_v2 = (
            "def compute_step(self, vals):\n"
            "    return sum(v * 10 for v in vals) * self.scale\n"
        )
        ok2, msg2 = CleanRoomSandbox.surgical_replace_block(script, "compute_step", new_method_v2)
        self.assertTrue(ok2, msg2)

        # 3. 故意提交函数名不匹配的代码块，验证被精准拦截且不污染原文件
        ok_bad, msg_bad = CleanRoomSandbox.surgical_replace_block(script, "Solver.compute_step", "def wrong_name(self, vals):\n    return 0\n")
        self.assertFalse(ok_bad)
        self.assertIn("不一致", msg_bad)

        # 执行替换后的脚本验证结果完全正确：(2+3+4)*10 * 2.0 = 180.0
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, check=True)
        self.assertAlmostEqual(float(proc.stdout.strip()), 180.0)

    def test_03_ast_forensic_contracts_obsolete_models_wheel_reinvention_and_a_data(self) -> None:
        """测试 §2.3, §4.2, §5.6, §7.6.2：过时模型拦截、手搓轮子拦截、多模态完整性 A_data、伪消融变量与三大偷懒陷阱"""
        parent_code = (
            "def solve(x):\n"
            "    lr = 0.01\n"
            "    return sum(x) * lr\n"
        )
        # 1. 违规使用过时模型 LogisticRegression + 手搓 def k_fold + 遗漏 geometry.xyz 模态
        bad_contract_code = (
            "from sklearn.linear_model import LogisticRegression\n"
            "def k_fold(data, k=5):\n"
            "    return data\n"
            "def solve(x):\n"
            "    df = 'train.csv'\n"
            "    return 0\n"
        )
        rep1 = ASTCodeInspector.inspect_code(
            candidate_code=bad_contract_code,
            obsolete_blacklist=["LogisticRegression / Ridge as final model"],
            required_data_modalities=["train.csv", "geometry.xyz"],
            enforce_data_completeness=True,
        )
        self.assertFalse(rep1.passed)
        self.assertTrue(any("手搓基础工具函数" in v for v in rep1.contract_violations))
        self.assertTrue(any("LogisticRegression" in v for v in rep1.contract_violations))
        self.assertEqual(rep1.unreferenced_modalities, ["geometry.xyz"])

        # 2. 测试三大偷懒陷阱：只改常数 + 导入 matplotlib 画图 + 吹嘘量子启发微批处理创新
        tweak_plot_code = (
            "import matplotlib.pyplot as plt\n"
            "from archive.ledger.primitives.fast_ops import fast_clip\n"
            "def solve(x):\n"
            "    lr = 0.005\n"
            "    return sum(x) * lr\n"
        )
        # 与含相同骨架的父代码比对结构改动率
        parent_with_import = (
            "import matplotlib.pyplot as plt\n"
            "from archive.ledger.primitives.fast_ops import fast_clip\n"
            "def solve(x):\n"
            "    lr = 0.01\n"
            "    return sum(x) * lr\n"
        )
        rep2 = ASTCodeInspector.inspect_code(
            candidate_code=tweak_plot_code,
            parent_code=parent_with_import,
            operator_description="Quantum-inspired holistic micro-batch gradient accumulation",
        )
        self.assertEqual(rep2.structural_diff_ratio, 0.0)
        self.assertTrue(rep2.is_superficial_tweak)
        self.assertEqual(rep2.novelty_classification, "BASELINE_ENGINEERING")
        self.assertEqual(rep2.imported_archive_primitives, ["fast_ops"])
        self.assertTrue(any("QUALITATIVE_VISUALIZATION_TRAP" in t for t in rep2.attractor_traps_detected))

    def test_04_hook_gate_kernel_vault_readonly_shell_and_cross_slot_snooping(self) -> None:
        """测试 §5.2：PreToolUse Hook 对保险箱、只读区终端重定向与跨槽位偷看的精准拦截"""
        hook_script = PLUGIN_ROOT / "bin" / "hook_gate.py"

        def run_hook(payload: dict) -> dict:
            p = subprocess.run(
                [sys.executable, str(hook_script)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            return json.loads(p.stdout.strip())

        # 1. 拦截读取 .kernel_vault
        self.assertEqual(
            run_hook({"toolCall": {"name": "read_file", "args": {"Path": "d:/proj/.kernel_vault/hmac_secret.key"}}})["decision"],
            "deny",
        )
        # 2. 拦截通过 PowerShell 重定向篡改 shared_readonly
        self.assertEqual(
            run_hook({"toolCall": {"name": "run_command", "args": {"CommandLine": "echo hacked > d:/proj/shared_readonly/task_config.yaml"}}})["decision"],
            "deny",
        )
        # 3. 拦截跨槽位偷看 (../slot_02 或同时引用两个槽位)
        self.assertEqual(
            run_hook({"toolCall": {"name": "read_file", "args": {"Path": "d:/proj/worktrees/slot_01_node-001/../slot_02_node-002/src/main.py"}}})["decision"],
            "deny",
        )
        self.assertEqual(
            run_hook({"toolCall": {"name": "run_command", "args": {"CommandLine": "cp d:/proj/worktrees/slot_01/a.py d:/proj/worktrees/slot_02/a.py"}}})["decision"],
            "deny",
        )
        # 4. 放行正常的孤岛内部读写与只读区读取
        self.assertEqual(
            run_hook({"toolCall": {"name": "read_file", "args": {"Path": "d:/proj/shared_readonly/archive/ARCHIVE_INDEX.md"}}})["decision"],
            "allow",
        )

    def test_05_five_item_legacy_primitives_claims_cross_lineage_citations_and_retraction_tree(self) -> None:
        """测试 §3.2 & §3.3：原语入库、防同血统自引刷分、跨血统有效引用计数与错误结论依赖树撤回"""
        engine = GreatWallEngine(self.tmp_dir)
        engine.init_campaign(task_id="CITE_TEST", task_description="测试原语跨血统引用计数")
        engine.lock_opening_distillation(
            orthogonal_families=[
                {"family_id": "FAM-A", "family_name": "Family A"},
                {"family_id": "FAM-B", "family_name": "Family B"},
            ],
            anchor_baseline_code="def solve(x):\n    return float(sum(x))\n",
        )

        # 1. FAM-A 节点提交一个带单测的原语 fast_scale.py 与一条引理 CLM-A1
        alloc_a = engine.allocate_exploration_slot("FAM-A", "solve", "提交原语 fast_scale")
        slot_a = alloc_a["slot_id"]
        island_a = Path(alloc_a["island_path"])
        engine.surgical_replace_in_slot(slot_a, "solve", "def solve(x):\n    return float(sum(v * 2 for v in x))\n")
        engine.evaluate_slot(slot_a)

        prim_dir = island_a / "legacy_out" / "primitives"
        prim_dir.mkdir(parents=True, exist_ok=True)
        (prim_dir / "fast_scale.py").write_text(
            'def scale_positive(vals: list[float], factor: float = 3.0) -> float:\n'
            '    """对正数元素执行加权求和并返回结果"""\n'
            '    return float(sum(v * factor for v in vals if v > 0))\n\n'
            'def test_scale_positive():\n'
            '    assert scale_positive([1.0, -2.0, 3.0], 2.0) == 8.0\n',
            encoding="utf-8",
        )
        (island_a / "legacy_out" / "epitaph.md").write_text("完成了正数加权原语抽离并验证通过，显著降低噪声干扰。", encoding="utf-8")
        (island_a / "legacy_out" / "claims.json").write_text(
            json.dumps([{"claim_id": "CLM-A1", "statement": "正数滤波可消除负异常值对线性求和的偏移", "depends_on": []}]),
            encoding="utf-8",
        )
        (island_a / "legacy_out" / "last_will_proposals.json").write_text(
            json.dumps([{"action_type": "GRAFT", "target_code_block": "solve", "falsifiable_hypothesis": "嫁接 fast_scale 到 FAM-B"}]),
            encoding="utf-8",
        )
        sub_a = engine.submit_legacy_and_release_slot(slot_a, steps_consumed=20)
        self.assertEqual(sub_a["status"], "OK")
        self.assertEqual(sub_a["admitted_primitives"], ["fast_scale.py"])
        self.assertEqual(sub_a["admitted_claims"], ["CLM-A1"])

        # 验证 diff.patch 已生成且 PRIMITIVES_API.md 零源码泄漏
        api_md = (self.tmp_dir / "shared_readonly" / "archive" / "PRIMITIVES_API.md").read_text(encoding="utf-8")
        self.assertIn("from archive.ledger.primitives.fast_scale import scale_positive", api_md)
        self.assertNotIn("for v in vals if v > 0", api_md)

        # 2. 同血统 FAM-A 的后续节点自己 import fast_scale：验证防自引机制生效，cross_lineage_citations 仍为 0！
        alloc_a2 = engine.allocate_exploration_slot("FAM-A", "solve", "同血统自引测试")
        slot_a2 = alloc_a2["slot_id"]
        island_a2 = Path(alloc_a2["island_path"])
        (island_a2 / "src" / "main.py").write_text(
            "from archive.ledger.primitives.fast_scale import scale_positive\n"
            "def solve(x):\n"
            "    return scale_positive(x, 2.5)\n",
            encoding="utf-8",
        )
        engine.evaluate_slot(slot_a2)
        (island_a2 / "legacy_out" / "epitaph.md").write_text("同血统内部调用原语测试完成，结果符合预期。", encoding="utf-8")
        (island_a2 / "legacy_out" / "last_will_proposals.json").write_text(
            json.dumps([{"action_type": "EXTEND", "target_code_block": "solve", "falsifiable_hypothesis": "继续测试"}]),
            encoding="utf-8",
        )
        sub_a2 = engine.submit_legacy_and_release_slot(slot_a2, steps_consumed=15)
        self.assertEqual(sub_a2["credited_cross_lineage_primitives"], [])

        # 3. 跨血统 FAM-B 节点 import fast_scale 并取得 PARETO_PROMOTE：验证 cross_lineage_citations 真实增加为 1！
        alloc_b = engine.allocate_exploration_slot("FAM-B", "solve", "跨血统嫁接 fast_scale")
        slot_b = alloc_b["slot_id"]
        island_b = Path(alloc_b["island_path"])
        (island_b / "src" / "main.py").write_text(
            "from archive.ledger.primitives.fast_scale import scale_positive\n"
            "def solve(x):\n"
            "    return scale_positive(x, 5.0)\n",
            encoding="utf-8",
        )
        engine.evaluate_slot(slot_b)
        (island_b / "legacy_out" / "epitaph.md").write_text("跨血统嫁接 FAM-A 的 fast_scale 原语成功，得分大幅跃升。", encoding="utf-8")
        (island_b / "legacy_out" / "claims.json").write_text(
            json.dumps([{"claim_id": "CLM-B1", "statement": "基于 CLM-A1 的 5 倍放大在 FAM-B 上同样收敛", "depends_on": ["CLM-A1"]}]),
            encoding="utf-8",
        )
        (island_b / "legacy_out" / "last_will_proposals.json").write_text(
            json.dumps([{"action_type": "EXTEND", "target_code_block": "solve", "falsifiable_hypothesis": "进一步调优"}]),
            encoding="utf-8",
        )
        sub_b = engine.submit_legacy_and_release_slot(slot_b, steps_consumed=20)
        self.assertEqual(sub_b["credited_cross_lineage_primitives"], ["fast_scale"])

        # 4. 撤回上游引理 CLM-A1，验证下游 CLM-B1 自动变为 NEEDS_REVALIDATION
        affected = engine.archive.retract_claim("CLM-A1", "在非平稳分布下发现反例")
        self.assertIn("CLM-A1", affected)
        self.assertIn("CLM-B1", affected)
        clm_b1 = engine.archive.query_l2_item("CLM-B1")["data"]
        self.assertEqual(clm_b1["status"], "NEEDS_REVALIDATION")

    def test_06_60_step_commitment_lock_barrier_proof_exemption_and_reflection_chamber(self) -> None:
        """测试 §7.1 & §7.6：60 步导师深挖承诺锁、BarrierProof 反例脚本沙箱验证提前豁免、以及满 60 步原位内省室契约"""
        engine = GreatWallEngine(self.tmp_dir)
        engine.init_campaign(task_id="LOCK_TEST", task_description="测试 60 步深挖锁与死路证明豁免")
        engine.lock_opening_distillation(
            orthogonal_families=[
                {"family_id": "FAM-DEAD", "family_name": "Dead End Family"},
                {"family_id": "FAM-GOOD", "family_name": "Promising Family"},
            ],
            anchor_baseline_code="def solve(x):\n    return float(sum(x))\n",
        )

        # 1. 在 FAM-DEAD 上仅投入 20 步 (< 60 步)，尝试无证明直接 hard_fork 到 FAM-GOOD -> 必须被 60 步承诺锁拦截！
        alloc1 = engine.allocate_exploration_slot("FAM-DEAD", "solve", "初步尝试")
        slot1 = alloc1["slot_id"]
        fork_blocked = engine.hard_fork_ancestor(
            slot_id=slot1,
            ancestor_commit=None,
            new_family_id="FAM-GOOD",
            new_targeted_block="solve",
            new_hypothesis="想提前溜走换方向",
        )
        self.assertEqual(fork_blocked["status"], "COMMITMENT_LOCK_ACTIVE")

        # 2. 在 slot1 中编写可执行的数学反例脚本 verify_barrier.py 与 barrier_proof.json，提交遗产证实 FAM-DEAD 为死路
        island1 = Path(alloc1["island_path"])
        engine.evaluate_slot(slot1)
        (island1 / "verify_barrier.py").write_text(
            "import sys\n"
            "# 构造奇异矩阵反例证明线性直接求逆在该边界恒崩溃\n"
            "det = 0.0\n"
            "assert det == 0.0\n"
            "print('BARRIER_VERIFIED: Singular matrix counterexample confirmed')\n",
            encoding="utf-8",
        )
        (island1 / "legacy_out" / "barrier_proof.json").write_text(
            json.dumps({
                "proof_id": "BARRIER-FAM-DEAD-01",
                "blocked_family_id": "FAM-DEAD",
                "impossibility_statement": "退化零行列式下直接求逆恒奇异，绝对不可能超过基线",
                "counterexample_script": "verify_barrier.py",
            }),
            encoding="utf-8",
        )
        # 附带了已证实的 barrier_proof.json，墓志铭中写“绝对不可能超过”完全合法通过！
        (island1 / "legacy_out" / "epitaph.md").write_text(
            "已通过 verify_barrier.py 反例脚本严格证明：退化零行列式下直接求逆绝对不可能超过基线。",
            encoding="utf-8",
        )
        (island1 / "legacy_out" / "last_will_proposals.json").write_text(
            json.dumps([{"action_type": "ORTHOGONAL", "target_code_block": "solve", "falsifiable_hypothesis": "转向 FAM-GOOD"}]),
            encoding="utf-8",
        )
        sub1 = engine.submit_legacy_and_release_slot(slot1, steps_consumed=20)
        self.assertEqual(sub1["status"], "OK")
        self.assertEqual(sub1["admitted_barrier_proofs"], ["BARRIER-FAM-DEAD-01"])

        # 验证此后若再向已证实死路的 FAM-DEAD 申请槽位，调度器直接拦截！
        alloc_dead_again = engine.allocate_exploration_slot("FAM-DEAD", "solve", "试图重蹈覆辙")
        self.assertEqual(alloc_dead_again["status"], "BLOCKED_BY_BARRIER_PROOF")

        # 3. 在 FAM-GOOD 上累计投入满 60 步，验证触发原位 3 轮内省室并持久化 ReflectionRecord
        alloc2 = engine.allocate_exploration_slot("FAM-GOOD", "solve", "深挖 60 步")
        slot2 = alloc2["slot_id"]
        island2 = Path(alloc2["island_path"])
        engine.evaluate_slot(slot2)
        (island2 / "legacy_out" / "epitaph.md").write_text("完成了 60 步完整参数与算子结构消融实验记录。", encoding="utf-8")
        (island2 / "legacy_out" / "last_will_proposals.json").write_text(
            json.dumps([{"action_type": "EXTEND", "target_code_block": "solve", "falsifiable_hypothesis": "进入下一阶段"}]),
            encoding="utf-8",
        )
        sub2 = engine.submit_legacy_and_release_slot(slot2, steps_consumed=60)
        self.assertTrue(sub2["trigger_60_step_reflection_chamber"])

        ref_res = engine.submit_reflection_record(
            lineage_id="LIN-FAM-GOOD",
            turn1_evidence_audit="前60步真实提分来自二阶差分算子，而非超参微调",
            turn2_attractor_diagnosis="未陷入定性画图或静态代理陷阱",
            turn3_pivot_decision="保持当前主干，未来20步嫁接正则化原语",
            next_20_steps_contract={"locked_block": "solve", "forbidden_actions": ["grid_search_lr"]},
        )
        self.assertEqual(ref_res["status"], "OK")
        self.assertTrue(Path(ref_res["reflection_file"]).exists())

    def test_07_soft_flush_rollback_and_meta_pattern_auto_patch(self) -> None:
        """测试 §6.2.2 & §7.6.4：原地软清栈 (Soft Flush) 脏代码回滚置顶警告 + 连续 3 次同因失败自动生成 Meta-Pattern 补丁"""
        engine = GreatWallEngine(self.tmp_dir)
        engine.init_campaign(task_id="FLUSH_META", task_description="测试软清栈与共性死因补丁")
        engine.lock_opening_distillation(
            orthogonal_families=[{"family_id": "FAM-01", "family_name": "Main Family"}],
            anchor_baseline_code="def solve(x):\n    return 42.0\n",
        )

        alloc = engine.allocate_exploration_slot("FAM-01", "solve", "测试软清栈")
        slot_id = alloc["slot_id"]
        island_dir = Path(alloc["island_path"])

        # 把孤岛代码改坏
        (island_dir / "src" / "main.py").write_text("def solve(x):\n    raise RuntimeError('Dirty broken edit')\n", encoding="utf-8")
        flush_res = engine.soft_flush_slot(slot_id, failure_epitaph="手写矩阵广播维度写反导致 RuntimeError")
        self.assertEqual(flush_res["status"], "OK")
        # 验证代码已恢复为 42.0 且 scoped_brief.md 顶部已注入红牌警告
        self.assertIn("42.0", (island_dir / "src" / "main.py").read_text(encoding="utf-8"))
        self.assertIn("原地软清栈警告", (island_dir / "scoped_brief.md").read_text(encoding="utf-8"))

        # 模拟 3 次命中同一 failure_category="OOM_FULL_PAIRWISE_MATRIX"，验证自动写入 pitfall_guardrails.md
        for i in range(3):
            engine.archive._append_jsonl(
                engine.archive.records_file,
                {
                    "record_id": f"REC-OOM-{i}",
                    "node_id": f"NODE-OOM-{i}",
                    "family_id": "FAM-01",
                    "lineage_id": "LIN-FAM-01",
                    "commit_hash": "DUMMY",
                    "tried_mechanism": "Full NxN distance matrix",
                    "failure_category": "OOM_FULL_PAIRWISE_MATRIX",
                    "failure_summary": "在 N=100,000 时构造全量稠密距离矩阵导致 64GB 内存瞬间溢出",
                },
            )
        patched = engine.archive._detect_and_patch_meta_patterns_unlocked()
        self.assertIn("OOM_FULL_PAIRWISE_MATRIX", patched)
        guardrails_txt = (self.tmp_dir / "shared_readonly" / "distilled" / "pitfall_guardrails.md").read_text(encoding="utf-8")
        self.assertIn("[META-PATTERN:OOM_FULL_PAIRWISE_MATRIX]", guardrails_txt)

    def test_08_cross_branch_differential_testing_and_retroactive_errata_revival(self) -> None:
        """测试 §7.3.2 & §7.4：跨分支无标签差分互测定位分歧算例 + 评测集错题热勘误追溯平反被误杀分支"""
        engine = GreatWallEngine(self.tmp_dir)
        engine.init_campaign(task_id="DIFF_ERRATA", task_description="测试差分互测与错题热勘误")
        engine.lock_opening_distillation(
            orthogonal_families=[{"family_id": "FAM-01", "family_name": "Main"}],
            anchor_baseline_code="def evaluate():\n    return {'frozen_score': 70.0, 'live_score': 70.0}\n",
        )

        # 1. 跨分支差分互测：分支 A 对负数正常处理，分支 B 在负数输入时符号写反 -> 自动抓出负数分歧算例
        script_a = self.tmp_dir / "branch_a.py"
        script_b = self.tmp_dir / "branch_b.py"
        script_a.write_text("def solve(x):\n    return sum(abs(v) for v in x)\n", encoding="utf-8")
        script_b.write_text("def solve(x):\n    return sum(v for v in x)\n", encoding="utf-8")

        diff_res = engine.evaluator.run_differential_test(
            script_a_path=script_a,
            script_b_path=script_b,
            stress_inputs=[[1, 2, 3], [-10, 10], [0]],
        )
        self.assertEqual(diff_res["status"], "OK")
        self.assertFalse(diff_res["consistent"])
        self.assertEqual(len(diff_res["divergent_cases"]), 1)
        self.assertEqual(diff_res["divergent_cases"][0]["input"], [-10, 10])

        # 2. 评测集错题热勘误追溯平反：
        # 某优秀节点在 case_1 (95分), case_2 (93分) 上远超基线 (70分)，但因为错题 case_buggy_nan 得 0 分，拉低均分至 62.67 被判 DEAD_END_ARCHIVE
        alloc = engine.allocate_exploration_slot("FAM-01", "evaluate", "被错题坑害的优秀节点")
        slot_id = alloc["slot_id"]
        island_dir = Path(alloc["island_path"])
        (island_dir / "src" / "main.py").write_text(
            "def evaluate():\n"
            "    return {'case_scores': {'case_1': 95.0, 'case_2': 93.0, 'case_buggy_nan': 0.0}}\n",
            encoding="utf-8",
        )
        eval_before = engine.evaluate_slot(slot_id)
        self.assertAlmostEqual(eval_before["scores"]["frozen_benchmark"], 62.666667, places=4)
        self.assertEqual(eval_before["triage_tier"], "DEAD_END_ARCHIVE")

        # 触发热勘误废弃 case_buggy_nan -> 自动重算历史账本，该节点均分恢复为 94.0 (> 70.0)，原地平反晋级 PARETO_PROMOTE！
        errata_res = engine.evaluator.deprecate_errata_case(
            case_id="case_buggy_nan",
            reason="Generator division by zero produced NaN",
            anchor_s0_score=70.0,
            higher_is_better=True,
        )
        self.assertEqual(errata_res["status"], "OK")
        self.assertEqual(len(errata_res["revived_branches"]), 1)
        self.assertAlmostEqual(errata_res["revived_branches"][0]["new_score"], 94.0)
        self.assertEqual(errata_res["revived_branches"][0]["new_tier"], "PARETO_PROMOTE")

    def test_09_windows_job_object_64bit_process_tree_kill_and_concurrent_file_locks(self) -> None:
        """测试 §5.4 & §6.3：64 位 Windows Job Object 超时连坐强杀与多线程并发写排行榜/文件锁零损坏压测"""
        # 1. 启动一个故意死循环并派生子进程的恶意脚本，限时 1.0 秒，验证 Job Object 干净利落强杀且返回峰值内存
        runaway_code = (
            "import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "data = bytearray(15 * 1024 * 1024)\n"
            "time.sleep(60)\n"
        )
        sub_res = run_bounded_subprocess(
            cmd=[sys.executable, "-c", runaway_code],
            cwd=self.tmp_dir,
            shared_readonly_dir=self.tmp_dir,
            timeout_sec=1.0,
            max_memory_mb=1024,
        )
        self.assertTrue(sub_res.is_timeout)
        self.assertEqual(sub_res.exit_code, 124)

        # 2. 并发压测：8 个线程同时调用 update_leaderboard 写同一个 JSON 文件，验证 InterProcessFileLock 零竞争零损坏
        archive = LightweightArchive(self.tmp_dir / "shared_readonly")

        def worker(idx: int) -> int:
            return archive.update_leaderboard(
                node_id=f"NODE-CONC-{idx:02d}",
                family_id="FAM-CONC",
                commit_hash=f"COMMIT_{idx:04d}",
                frozen_score=float(50 + idx),
                live_score=float(50 + idx),
                wall_time_sec=0.5,
                summary=f"Concurrent update {idx}",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            ranks = list(pool.map(worker, range(16)))
        self.assertEqual(len(ranks), 16)
        lb_entries = json.loads(archive.leaderboard_file.read_text(encoding="utf-8"))["entries"]
        self.assertEqual(len(lb_entries), 16)
        self.assertEqual(lb_entries[0]["frozen_score"], 65.0)

    def test_10_mcp_stdio_jsonrpc_full_9_tools_and_final_delivery_anti_bluff(self) -> None:
        """测试 §8.3：MCP Stdio Server 9 大工具全协议交互与终局防吹牛五件套交付信封"""
        server_script = PLUGIN_ROOT / "bin" / "gw_mcp_server.py"
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "gw_init_campaign",
                    "arguments": {
                        "workspaceRoot": str(self.tmp_dir),
                        "taskId": "FINAL_E2E",
                        "taskDescription": "全链路 MCP 协议与终局交付测试",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "gw_lock_distillation",
                    "arguments": {
                        "workspaceRoot": str(self.tmp_dir),
                        "orthogonalFamilies": [{"family_id": "FAM-01", "family_name": "Vectorized DP"}],
                        "anchorBaselineCode": "def solve(x):\n    return float(sum(x))\n",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "gw_compile_delivery",
                    "arguments": {
                        "workspaceRoot": str(self.tmp_dir),
                        "executiveSummaryMd": "包含未完成占位符 TODO 的草稿",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "gw_compile_delivery",
                    "arguments": {
                        "workspaceRoot": str(self.tmp_dir),
                        "executiveSummaryMd": "### 终局核心结论\n已完成全套清洁室沙箱实验验证，所有指标100%源自HMAC防伪收据。",
                    },
                },
            },
        ]
        input_lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in requests) + "\n"
        proc = subprocess.run(
            [sys.executable, str(server_script)],
            input=input_lines,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        responses = [json.loads(line) for line in proc.stdout.strip().splitlines() if line.strip()]
        self.assertEqual(len(responses), 6)

        tools = responses[1]["result"]["tools"]
        self.assertEqual(len(tools), 9)

        # 验证含 TODO 的终局报告被拦截
        blocked_res = json.loads(responses[4]["result"]["content"][0]["text"])
        self.assertEqual(blocked_res["status"], "DELIVERY_BLOCKED_PLACEHOLDERS")

        # 验证清理占位符后的终局报告成功生成五件套目录
        ok_res = json.loads(responses[5]["result"]["content"][0]["text"])
        self.assertEqual(ok_res["status"], "OK")
        self.assertTrue((self.tmp_dir / "final_delivery" / "01_executive_report.md").exists())
        self.assertTrue((self.tmp_dir / "final_delivery" / "03_claim_evidence_ledger.json").exists())
        self.assertTrue((self.tmp_dir / "final_delivery" / "04_reproduce_all.ps1").exists())
        self.assertTrue((self.tmp_dir / "final_delivery" / "05_boundary_and_dead_ends_report.md").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
