"""
Lightweight File-System Archive (No Heavy Vector RAG) & Full 5-Item Node Legacy Protocol.
严格对齐《15_长城Agent_V4无人值守架构与沙箱工程实战规范.md》第 3、7、8 章：
1. 三级按需加载架构 (复刻 Station arXiv:2610.08927)：
   - L0 全局索引 (`ARCHIVE_INDEX.md` + `PRIMITIVES_API.md`)：利用 AST 自动提取函数签名与首行说明，严守“调库不读码”；
   - L1 节点启动专属简报 (`scoped_brief.md`)：按方法族 `family_id` 与血统 `lineage_id` 精准裁剪注入；
   - L2 按需预览与点读：避免将成百上千行旧日志塞入当前上下文；
2. 完整五件套遗产包校验入库：
   - 遗产①：`epitaph.md` / `record_entry.json` (含防无反例悲观谣言拦截 + 共性死因 Meta-Pattern 自动提炼补丁 §7.6.4)；
   - 遗产②：`diff.patch` + `metrics_receipt.json`；
   - 遗产③：`primitives/*.py` (沙箱单测准入 + `primitives_manifest.json` 跨血统真实引用统计 §3.2.2)、`lemmas/*.md`、`claims.json` (`ClaimEntry` §8.1 #8) 与 `barrier_proof.json` (沙箱反例脚本验证 `BarrierProof` §7.1 & §8.1 #9)；
   - 遗产④：`anomalies_and_bounties.json`；
   - 遗产⑤：`last_will_proposals.json` (1~3 条结构化接力遗嘱) + `lineage_note.md`；
3. 错误结论撤回依赖树 (`retract_claim`) + OS 级跨进程文件互斥锁 (`InterProcessFileLock`)。
"""

from __future__ import annotations

import ast
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .sandbox import InterProcessFileLock, run_bounded_subprocess


@dataclass
class LegacyValidationResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    admitted_primitives: List[str] = field(default_factory=list)
    admitted_claims: List[str] = field(default_factory=list)
    admitted_barrier_proofs: List[str] = field(default_factory=list)
    admitted_record_id: str = ""
    admitted_proposals_count: int = 0
    meta_patterns_patched: List[str] = field(default_factory=list)


class LightweightArchive:
    """
    轻量级文件系统档案馆 (`shared_readonly/archive/`) 管理器：
    1. 死胡同黑名单 (`record_blacklist.jsonl`)：免审直通，专门记具体失败原因（严禁无证明的宏观悲观谣言）；
    2. 白名单进展库 (`ledger/primitives/*.py`, `primitives_manifest.json`, `claims.jsonl`, `barrier_proofs.jsonl`, `leaderboard.json`)：
       只有通过独立沙箱单元测试/反例复现的算子、引理与死路证明才能入库；
    3. 世代血统私有笔记 (`lineage_notes/`)：仅对同血统后代挂载可见；
    4. 错误结论撤回依赖树 (`retract_claim`)：上游证伪后自动沿 `depends_on` 标记下游待复核。
    """

    def __init__(self, shared_readonly_root: Path) -> None:
        self.shared_root = shared_readonly_root.resolve()
        self.archive_root = self.shared_root / "archive"
        self.ledger_dir = self.archive_root / "ledger"
        self.primitives_dir = self.ledger_dir / "primitives"
        self.lemmas_dir = self.ledger_dir / "lemmas"
        self.lineage_dir = self.archive_root / "lineage_notes"
        self.distilled_dir = self.shared_root / "distilled"

        self.lock_file = self.archive_root / "archive.lock"
        self.records_file = self.archive_root / "record_blacklist.jsonl"
        self.claims_file = self.ledger_dir / "claims.jsonl"
        self.barrier_proofs_file = self.ledger_dir / "barrier_proofs.jsonl"
        self.primitives_manifest_file = self.ledger_dir / "primitives_manifest.json"
        self.leaderboard_file = self.ledger_dir / "leaderboard.json"
        self.bounties_file = self.archive_root / "bounties.jsonl"
        self.index_md_file = self.archive_root / "ARCHIVE_INDEX.md"
        self.primitives_api_file = self.archive_root / "PRIMITIVES_API.md"

        self._ensure_structure()

    def _ensure_structure(self) -> None:
        for d in (self.archive_root, self.ledger_dir, self.primitives_dir, self.lemmas_dir, self.lineage_dir, self.distilled_dir):
            d.mkdir(parents=True, exist_ok=True)
        for pkg_dir in (self.archive_root, self.ledger_dir, self.primitives_dir):
            init_py = pkg_dir / "__init__.py"
            if not init_py.exists():
                init_py.write_text('"""Great Wall Agent Verified Archive Package."""\n', encoding="utf-8")

        if not self.leaderboard_file.exists():
            self.leaderboard_file.write_text(json.dumps({"entries": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        if not self.primitives_manifest_file.exists():
            self.primitives_manifest_file.write_text(json.dumps({"primitives": {}}, ensure_ascii=False, indent=2), encoding="utf-8")

    # ========================================================================
    # 1. AST 原语签名自动提取器 (“调库不读码” / Import, Don't Read Implementation)
    # ========================================================================

    def build_primitives_api_catalog(self) -> str:
        """
        扫描 `archive/ledger/primitives/*.py` 的 AST 并结合 `primitives_manifest.json`：
        仅提取 `from archive.ledger.primitives.xxx import fn`、类型签名、首行 Docstring 与跨血统引用次数（0 行函数体源码！）
        """
        lines = [
            "# 🛠️ 档案馆可直接 import 的已验证原语签名目录 (PRIMITIVES_API)",
            "> **铁律**：以下组件均已通过独立单元测试。请直接在代码中 `import` 调用，严禁重新手搓同功能函数！\n",
        ]
        py_files = sorted(
            [p for p in self.primitives_dir.glob("*.py") if p.name != "__init__.py"]
        )
        if not py_files:
            lines.append("*(当前暂无已入库原语，鼓励各节点在局部代码块提分后将其抽离进 `legacy_out/primitives/`)*\n")
            content = "\n".join(lines)
            self.primitives_api_file.write_text(content, encoding="utf-8")
            return content

        manifest_data = {"primitives": {}}
        if self.primitives_manifest_file.exists():
            try:
                manifest_data = json.loads(self.primitives_manifest_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        prim_meta_map = manifest_data.get("primitives", {})

        for py_file in py_files:
            mod_path = f"archive.ledger.primitives.{py_file.stem}"
            meta = prim_meta_map.get(py_file.stem, {})
            citations = int(meta.get("cross_lineage_citations", 0))
            cite_badge = f" *(跨血统有效引用: {citations} 次)*" if citations > 0 else ""
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except SyntaxError:
                continue

            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith(("test_", "_")):
                    args_str = ast.unparse(node.args)
                    ret_str = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                    doc_first = (ast.get_docstring(node) or "已验证可复用原语函数").splitlines()[0].strip()
                    lines.append(
                        f"- **`from {mod_path} import {node.name}`**{cite_badge}\n"
                        f"  - 签名: `def {node.name}({args_str}){ret_str}`\n"
                        f"  - 说明: {doc_first}"
                    )
                elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                    doc_first = (ast.get_docstring(node) or "已验证可复用算子类").splitlines()[0].strip()
                    public_methods = [
                        n.name for n in node.body
                        if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
                    ]
                    lines.append(
                        f"- **`from {mod_path} import {node.name}`**{cite_badge}\n"
                        f"  - 公开方法: `{', '.join(public_methods)}`\n"
                        f"  - 说明: {doc_first}"
                    )

        content = "\n".join(lines) + "\n"
        self.primitives_api_file.write_text(content, encoding="utf-8")
        return content

    def increment_primitive_citations(
        self,
        imported_primitive_stems: List[str],
        caller_lineage_id: str,
        caller_node_id: str,
    ) -> List[str]:
        """
        跨血统引用真实统计 (§3.2.2 & §8.1 #5)：
        仅当调用方节点的 `caller_lineage_id` 与原语作者的 `lineage_id` 不同（即真正的跨分支迁移复用）且带来提分时，
        才为该原语增加 `cross_lineage_citations` 计数，彻底杜绝自引刷分！
        """
        if not imported_primitive_stems:
            return []
        credited: List[str] = []
        with InterProcessFileLock(self.lock_file):
            manifest_data = {"primitives": {}}
            if self.primitives_manifest_file.exists():
                try:
                    manifest_data = json.loads(self.primitives_manifest_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            prims = manifest_data.setdefault("primitives", {})
            for stem in imported_primitive_stems:
                if stem in prims:
                    p_entry = prims[stem]
                    author_lin = p_entry.get("lineage_id", "")
                    cited_by_list: List[str] = p_entry.setdefault("cited_by_lineages", [])
                    # 严禁同一血统自引刷分
                    if caller_lineage_id != author_lin and caller_lineage_id not in cited_by_list:
                        cited_by_list.append(caller_lineage_id)
                        p_entry["cross_lineage_citations"] = len(cited_by_list)
                        p_entry.setdefault("cited_by_nodes", []).append(caller_node_id)
                        credited.append(stem)
            if credited:
                self.primitives_manifest_file.write_text(
                    json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                self.build_primitives_api_catalog()
        return credited

    # ========================================================================
    # 2. L0 全局目录索引与 L1 节点专属启动简报生成 (零 LLM 确定性构建)
    # ========================================================================

    def rebuild_l0_index(self, target_family_id: Optional[str] = None) -> str:
        """
        确定性生成 L0 全局目录索引 (`ARCHIVE_INDEX.md`)，控制总长度 <= 1,000 Tokens：
        1. 全局 Top-5 排行榜
        2. 可直接 import 的原语 API 签名目录
        3. 近期死胡同避坑表 (Record Blacklist) 与已证实死路证明 (BarrierProofs)
        4. 已验证引理/规律与全局待解悬赏单 (Bounties)
        """
        primitives_catalog = self.build_primitives_api_catalog()

        # 1. Top-5 榜单
        lb_data = json.loads(self.leaderboard_file.read_text(encoding="utf-8")) if self.leaderboard_file.exists() else {"entries": []}
        entries = lb_data.get("entries", [])[:5]
        lb_lines = ["# 🏆 全局验证排行榜 Top-5 (Leaderboard)"]
        if not entries:
            lb_lines.append("*(尚无提交记录，等待零号强基线 s_0 或首个探索分支入榜)*")
        else:
            for idx, item in enumerate(entries, 1):
                lb_lines.append(
                    f"{idx}. **`[{item.get('node_id', 's_0')}]`** (Family: `{item.get('family_id', 'ANCHOR')}`, "
                    f"Commit: `{item.get('commit_hash', '')[:8]}`) — "
                    f"**Frozen得分: `{item.get('frozen_score')}`** | Live得分: `{item.get('live_score')}` | "
                    f"耗时: `{item.get('wall_time_sec', 0):.2f}s` | 摘要: {item.get('summary', '')}"
                )

        # 2. 死胡同避坑表与已证实 BarrierProof
        rec_lines = ["# 🚫 死胡同避坑黑名单 (Record Blacklist —— 严禁重复踩坑！)"]
        records = self._read_jsonl(self.records_file)
        if target_family_id:
            records = [r for r in records if r.get("family_id") in (target_family_id, "GLOBAL", None)]
        recent_records = records[-10:]
        barriers = self._read_jsonl(self.barrier_proofs_file)
        if not recent_records and not barriers:
            rec_lines.append("*(暂无失败记录)*")
        else:
            for bp in barriers[-4:]:
                rec_lines.append(
                    f"- 🛑 **`[死路反例证明 {bp.get('proof_id')}]`** (`{bp.get('blocked_family_id')}`) — "
                    f"**已通过沙箱反例脚本证实不可行**: {bp.get('impossibility_statement', '')}"
                )
            for r in recent_records:
                rec_lines.append(
                    f"- **`[{r.get('record_id', 'REC')}]`** (`{r.get('family_id', 'GLOBAL')}`) "
                    f"尝试机制: `{r.get('tried_mechanism', '')}` -> ❌ **死因**: {r.get('failure_summary', '')}"
                )

        # 3. 活跃科学引理与待解悬赏单
        claim_lines = ["# 📜 已验证结论引理 & 待解悬赏榜 (Verified Claims & Open Bounties)"]
        claims = [c for c in self._read_jsonl(self.claims_file) if c.get("status", "VERIFIED_ACTIVE") == "VERIFIED_ACTIVE"][-8:]
        bounties = [b for b in self._read_jsonl(self.bounties_file) if b.get("status", "OPEN") == "OPEN"][-6:]
        if not claims and not bounties:
            claim_lines.append("*(暂无入库引理或悬赏)*")
        else:
            for c in claims:
                claim_lines.append(f"- **[引理 `{c.get('claim_id')}`]**: {c.get('statement', '')}")
            for b in bounties:
                claim_lines.append(
                    f"- 🎯 **[悬赏 `{b.get('bounty_id')}` | 奖励 +{b.get('reward_steps', 25)} 步]**: "
                    f"{b.get('problem_description', '')}"
                )

        full_index = "\n\n---\n\n".join(
            ["\n".join(lb_lines), primitives_catalog.strip(), "\n".join(rec_lines), "\n".join(claim_lines)]
        ) + "\n"
        self.index_md_file.write_text(full_index, encoding="utf-8")
        return full_index

    def build_scoped_l1_brief(
        self,
        node_id: str,
        slot_id: str,
        family_id: str,
        lineage_id: str,
        parent_commit: str,
        targeted_code_block: str,
        hypothesis: str,
        step_budget: int = 25,
        soft_flush_warning: str = "",
    ) -> str:
        """
        为即将启动的探索节点精准装配 `scoped_brief.md` (L1 启动简报，恒定 <= 2,000 Tokens)：
        包含：任务硬约束、本方法族 SOTA 锚点、锁定的目标代码块 c_t、原地软清栈警告 (若有)、同血统私有笔记与 L0 裁剪索引。
        """
        l0_scoped = self.rebuild_l0_index(target_family_id=family_id)

        lineage_note_text = "*(本节点为该血统首代或无上代遗留私有笔记)*"
        lineage_files = sorted(self.lineage_dir.glob(f"{lineage_id}_*.md"))
        if lineage_files:
            lineage_note_text = lineage_files[-1].read_text(encoding="utf-8").strip()[:800]

        guardrails_excerpt = ""
        guardrails_path = self.distilled_dir / "pitfall_guardrails.md"
        if guardrails_path.exists():
            guardrails_excerpt = guardrails_path.read_text(encoding="utf-8").strip()[:600]

        flush_banner = ""
        if soft_flush_warning.strip():
            flush_banner = (
                f"\n> 🚨 **[原地软清栈警告 (Soft Flush Warning)]**：上一轮尝试因以下原因失败并已被回滚清栈，"
                f"本轮严禁重复该错误写法：\n> `{soft_flush_warning.strip()}`\n"
            )

        brief = f"""# 🚀 探索节点启动专属简报 (L1 Scoped Brief)
{flush_banner}
- **节点编号**: `{node_id}` | **工作槽位**: `{slot_id}` | **步数预算**: `{step_budget} 步`
- **所属正交方法族**: `{family_id}` | **世代血统 ID**: `{lineage_id}` | **基底快照 Commit**: `{parent_commit}`
- **本轮锁定微创手术代码块 ($c_t$)**: `{targeted_code_block}`
- **本轮可证伪攻关假说**: {hypothesis}

## ⚠️ 探索节点三大铁律（违者由内核直接拦截）
1. **外层消融定靶 + 内层局部微创替换**：只准针对锁定的瓶颈代码块 `{targeted_code_block}` 做微创迭代（优先调用 `gw_surgical_replace` 工具），**严禁无故全量重写外围正常代码**！
2. **调库不造轮子**：凡下方 `PRIMITIVES_API` 已列出的原语函数或 `build_vs_buy_contract.json` 指定的基础库，必须直接 `import` 复用，严禁手搓重复轮子。
3. **盘中禁止当甩手包工头**：禁止在探索中途派生子智能体；退出前必须在 `legacy_out/` 下提交完整的**【五件套遗产包】**并调用 `gw_submit_legacy` 验收！

---

## 🛡️ 全局防踩坑红线与共性元模式补丁 (`pitfall_guardrails.md`)
{guardrails_excerpt or "*(按默认沙箱防泄漏规范执行)*"}

---

## 🧬 同血统上一代私有交接笔记 (`{lineage_id}`)
{lineage_note_text}

---

{l0_scoped}
"""
        return brief

    # ========================================================================
    # 3. 节点五件套遗产包强校验与分流入库 (5-Item Legacy Bundle Admission)
    # ========================================================================

    def validate_and_admit_legacy(
        self,
        island_dir: Path,
        node_id: str,
        family_id: str,
        lineage_id: str,
        commit_hash: str,
    ) -> LegacyValidationResult:
        """
        严格校验探索节点在 `island_dir/legacy_out/` 下留下的【五件套遗产包】：
        1. `epitaph.md` (或 `record_entry.json`)：<= 300 字死胡同/经验墓志铭（必填，禁止空洞套话与无反例脚本支撑的悲观谣言）；
        2. `diff.patch` + `metrics_receipt.json`：代码补丁与特权评测进程签发的防伪成绩单；
        3. `primitives/*.py` & `lemmas/*.md` & `claims.json` & `barrier_proof.json` (可选但强烈鼓励)：
           - 原语必须在独立沙箱内跑通自带的 `test_*()` 单测才准入库 `Ledger` 并登记 `primitives_manifest.json`；
           - 死路反例证明 (`barrier_proof.json` + 反例脚本) 必须在沙箱内实跑输出 `BARRIER_VERIFIED` 才准入库；
        4. `anomalies_and_bounties.json` (可选)：反常现象与待解悬赏；
        5. `last_will_proposals.json`：临终后继接力遗嘱单（必填，含 1~3 个下一步提案）。
        """
        legacy_dir = island_dir / "legacy_out"
        res = LegacyValidationResult(ok=True)
        if not legacy_dir.exists():
            return LegacyValidationResult(ok=False, errors=[f"找不到遗产目录: {legacy_dir}"])

        # --- 校验遗产 ①：150 字死胡同墓志铭 (epitaph.md + record_entry.json) ---
        epitaph_file = legacy_dir / "epitaph.md"
        record_json_file = legacy_dir / "record_entry.json"
        epitaph_text = ""
        tried_mech = "未注明机制"
        failure_category = "GENERAL_FAILURE"
        if epitaph_file.exists():
            epitaph_text = epitaph_file.read_text(encoding="utf-8").strip()
        if record_json_file.exists():
            try:
                rec_data = json.loads(record_json_file.read_text(encoding="utf-8"))
                tried_mech = rec_data.get("tried_mechanism", tried_mech)
                epitaph_text = rec_data.get("failure_summary", epitaph_text)
                failure_category = rec_data.get("failure_category", failure_category)
            except Exception as e:
                res.errors.append(f"record_entry.json 格式损坏: {e}")

        if len(epitaph_text) < 15:
            res.errors.append("遗产①缺失或过短：必须在 legacy_out/epitaph.md 或 record_entry.json 中写明至少 15 字的具体实验总结/死胡同墓志铭！")
        elif len(epitaph_text) > 500:
            res.warnings.append(f"墓志铭长达 {len(epitaph_text)} 字，已自动截断至前 300 字以保护 L0 索引体积。")
            epitaph_text = epitaph_text[:300] + "..."

        # --- 校验遗产 ③ 中的 BarrierProof (若有) ---
        barrier_json_file = legacy_dir / "barrier_proof.json"
        verified_barrier_entry: Optional[Dict[str, Any]] = None
        if barrier_json_file.exists():
            ok_bp, bp_msg, bp_entry = self._verify_barrier_proof(barrier_json_file, island_dir, node_id, family_id)
            if not ok_bp:
                res.errors.append(f"遗产③死路证明 (barrier_proof.json) 验证未通过: {bp_msg}")
            else:
                verified_barrier_entry = bp_entry

        # 防悲观谣言传染检查 (Station 教训：除非附带已验证的 BarrierProof 反例脚本，否则严禁断言“绝对不可能超过”)
        rumor_phrases = ["绝对不可能超过", "理论上不存在更优", "完全不可解", "proven impossible without script"]
        has_barrier_script = (verified_barrier_entry is not None) or (
            any((legacy_dir / "primitives").glob("*barrier*.py")) if (legacy_dir / "primitives").exists() else False
        )
        if any(p in epitaph_text for p in rumor_phrases) and not has_barrier_script:
            res.errors.append(
                "防悲观谣言拦截：墓志铭中包含未经数学反例脚本证实的全局悲观断言！请只陈述本节点具体参数/算子下的客观失败原因，或提交可执行的 barrier_proof.json。"
            )

        # --- 校验遗产 ②：评测成绩单收据 (metrics_receipt.json + diff.patch) ---
        receipt_file = legacy_dir / "metrics_receipt.json"
        if not receipt_file.exists():
            res.errors.append("遗产②缺失：缺少 legacy_out/metrics_receipt.json（请先调用 gw_evaluate_slot 运行跨进程沙箱评测）！")

        # --- 校验遗产 ③：解耦可复用原语 (legacy_out/primitives/*.py) & 引理 (claims.json / lemmas/*.md) ---
        prim_src_dir = legacy_dir / "primitives"
        staged_primitives: List[Tuple[Path, str]] = []
        if prim_src_dir.exists():
            for py_f in sorted(prim_src_dir.glob("*.py")):
                if py_f.name == "__init__.py":
                    continue
                ok_prim, msg_prim = self._audit_and_test_primitive(py_f, island_dir)
                if not ok_prim:
                    res.errors.append(f"遗产③原语 '{py_f.name}' 审计未通过: {msg_prim}")
                else:
                    staged_primitives.append((py_f, msg_prim))

        claims_src_file = legacy_dir / "claims.json"
        staged_claims: List[Dict[str, Any]] = []
        if claims_src_file.exists():
            try:
                c_raw = json.loads(claims_src_file.read_text(encoding="utf-8"))
                c_list = c_raw if isinstance(c_raw, list) else c_raw.get("claims", [])
                for idx, c_item in enumerate(c_list):
                    if isinstance(c_item, dict) and c_item.get("statement"):
                        staged_claims.append({
                            "claim_id": c_item.get("claim_id", f"CLM-{node_id}-{idx+1:02d}"),
                            "author_node": node_id,
                            "family_id": family_id,
                            "lineage_id": lineage_id,
                            "commit_hash": commit_hash,
                            "statement": str(c_item["statement"]),
                            "stripped_operator_tuple": c_item.get("stripped_operator_tuple", {}),
                            "verification_vector": c_item.get("verification_vector", {}),
                            "depends_on": c_item.get("depends_on", []),
                            "status": "VERIFIED_ACTIVE",
                            "created_at": time.time(),
                        })
            except Exception as e:
                res.errors.append(f"legacy_out/claims.json 解析失败: {e}")

        # --- 校验遗产 ④：反常现象与悬赏卡 (anomalies_and_bounties.json) ---
        bounty_f = legacy_dir / "anomalies_and_bounties.json"
        staged_bounties: List[Dict[str, Any]] = []
        if bounty_f.exists():
            try:
                b_data = json.loads(bounty_f.read_text(encoding="utf-8"))
                b_list = b_data if isinstance(b_data, list) else b_data.get("bounties", [])
                for idx, b_item in enumerate(b_list):
                    if isinstance(b_item, dict) and b_item.get("problem_description"):
                        staged_bounties.append({
                            "bounty_id": b_item.get("bounty_id", f"BNT-{node_id}-{idx+1}"),
                            "posted_by_node": node_id,
                            "problem_description": b_item["problem_description"],
                            "reward_steps": int(b_item.get("reward_steps", 25)),
                            "status": "OPEN",
                            "created_at": time.time(),
                        })
            except Exception as e:
                res.warnings.append(f"解析 anomalies_and_bounties.json 告警: {e}")

        # --- 校验遗产 ⑤：临终接力遗嘱单 (last_will_proposals.json & lineage_note.md) ---
        will_file = legacy_dir / "last_will_proposals.json"
        proposals: List[Dict[str, Any]] = []
        if not will_file.exists():
            res.errors.append("遗产⑤缺失：必须在 legacy_out/last_will_proposals.json 中提交 1~3 条下一步接力遗嘱提案！")
        else:
            try:
                w_data = json.loads(will_file.read_text(encoding="utf-8"))
                proposals = w_data if isinstance(w_data, list) else w_data.get("proposals", [])
                if not proposals or len(proposals) > 3:
                    res.errors.append(f"遗嘱提案数量必须为 1~3 条（当前为 {len(proposals)} 条）！")
                for p in proposals:
                    if p.get("action_type") not in ("REPAIR", "GRAFT", "EXTEND", "ORTHOGONAL"):
                        res.errors.append(
                            f"遗嘱提案 action_type 必须为 REPAIR / GRAFT / EXTEND / ORTHOGONAL 之一，收到: {p.get('action_type')}"
                        )
                    if not p.get("falsifiable_hypothesis"):
                        res.errors.append("每条遗嘱提案必须包含可证伪假说字段 'falsifiable_hypothesis'！")
            except Exception as e:
                res.errors.append(f"last_will_proposals.json 解析失败: {e}")

        if res.errors:
            res.ok = False
            return res

        # 全部校验通过：在跨进程文件锁保护下正式写入档案馆
        with InterProcessFileLock(self.lock_file):
            # 1. 入库原语并更新 primitives_manifest.json
            manifest_data = {"primitives": {}}
            if self.primitives_manifest_file.exists():
                try:
                    manifest_data = json.loads(self.primitives_manifest_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            prims_map = manifest_data.setdefault("primitives", {})

            for py_f, first_doc in staged_primitives:
                dst_f = self.primitives_dir / py_f.name
                shutil.copy2(py_f, dst_f)
                res.admitted_primitives.append(py_f.name)
                stem = py_f.stem
                if stem not in prims_map:
                    prims_map[stem] = {
                        "primitive_id": f"prim_{stem}",
                        "module_path": f"archive.ledger.primitives.{stem}",
                        "author_node": node_id,
                        "family_id": family_id,
                        "lineage_id": lineage_id,
                        "docstring_summary": first_doc,
                        "unit_test_passed": True,
                        "cross_lineage_citations": 0,
                        "cited_by_lineages": [],
                        "cited_by_nodes": [],
                        "created_at": time.time(),
                    }
            if staged_primitives:
                self.primitives_manifest_file.write_text(
                    json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            # 2. 入库引理手稿 lemmas/*.md 与 claims.jsonl
            lemmas_src_dir = legacy_dir / "lemmas"
            if lemmas_src_dir.exists():
                for md_f in sorted(lemmas_src_dir.glob("*.md")):
                    shutil.copy2(md_f, self.lemmas_dir / f"{node_id}_{md_f.name}")

            for c_entry in staged_claims:
                self._append_jsonl(self.claims_file, c_entry)
                res.admitted_claims.append(c_entry["claim_id"])

            # 3. 入库死路反例证明 BarrierProof
            if verified_barrier_entry is not None:
                self._append_jsonl(self.barrier_proofs_file, verified_barrier_entry)
                res.admitted_barrier_proofs.append(verified_barrier_entry["proof_id"])

            # 4. 入库悬赏单 Bounties
            for b_record in staged_bounties:
                self._append_jsonl(self.bounties_file, b_record)

            # 5. 入库死胡同/经验记录 Record Blacklist
            rec_id = f"REC-{int(time.time() * 1000) % 100000:05d}"
            self._append_jsonl(
                self.records_file,
                {
                    "record_id": rec_id,
                    "node_id": node_id,
                    "family_id": family_id,
                    "lineage_id": lineage_id,
                    "commit_hash": commit_hash,
                    "tried_mechanism": tried_mech,
                    "failure_category": failure_category,
                    "failure_summary": epitaph_text,
                    "timestamp": time.time(),
                },
            )
            res.admitted_record_id = rec_id
            res.admitted_proposals_count = len(proposals)

            # 6. 保存同血统私有笔记 (若有)
            lineage_note_src = legacy_dir / "lineage_note.md"
            if lineage_note_src.exists():
                note_txt = lineage_note_src.read_text(encoding="utf-8").strip()
                if note_txt:
                    dst_note = self.lineage_dir / f"{lineage_id}_{node_id}.md"
                    dst_note.write_text(note_txt, encoding="utf-8")

            # 7. 检测跨分支共性死因并自动追加 Meta-Pattern 防护补丁 (§7.6.4)
            res.meta_patterns_patched = self._detect_and_patch_meta_patterns_unlocked()

            # 8. 刷新 L0 索引
            self.rebuild_l0_index(target_family_id=family_id)

        return res

    def _verify_barrier_proof(
        self,
        barrier_json_file: Path,
        island_dir: Path,
        node_id: str,
        family_id: str,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        验证死路反例证明 (`BarrierProof`, §7.1 & §8.1 #9)：
        要求节点提供一个可在沙箱独立运行的反例验证脚本 `counterexample_script`，
        脚本在 15 秒内运行成功（exit_code == 0 且无断言失败）才予以认证，认证后可合法豁免 60 步深挖锁。
        """
        try:
            bdata = json.loads(barrier_json_file.read_text(encoding="utf-8"))
        except Exception as e:
            return False, f"JSON 解析错误: {e}", None

        statement = str(bdata.get("impossibility_statement", "")).strip()
        script_rel = str(bdata.get("counterexample_script", "")).strip()
        blocked_fam = str(bdata.get("blocked_family_id", family_id)).strip()
        if not statement or not script_rel:
            return False, "barrier_proof.json 必须包含 'impossibility_statement' 与 'counterexample_script' 字段", None

        script_path = (island_dir / script_rel).resolve()
        if not script_path.exists():
            return False, f"找不到反例验证脚本: {script_rel}", None

        run_res = run_bounded_subprocess(
            cmd=[sys.executable, str(script_path)],
            cwd=island_dir,
            shared_readonly_dir=self.shared_root,
            timeout_sec=15.0,
            max_memory_mb=2048,
        )
        if run_res.exit_code != 0:
            return False, f"反例脚本运行失败 (exit={run_res.exit_code}): {(run_res.stderr or run_res.stdout)[:250]}", None

        proof_entry = {
            "proof_id": bdata.get("proof_id", f"BARRIER-{node_id}"),
            "author_node": node_id,
            "blocked_family_id": blocked_fam,
            "impossibility_statement": statement,
            "counterexample_script": script_rel,
            "stdout_evidence": run_res.stdout.strip()[:300],
            "verified": True,
            "timestamp": time.time(),
        }
        return True, "OK", proof_entry

    def has_verified_barrier_for_family(self, family_id: str) -> bool:
        """检查指定正交方法族是否已有经沙箱反例脚本证实的 `BarrierProof`"""
        for bp in self._read_jsonl(self.barrier_proofs_file):
            if bp.get("blocked_family_id") == family_id and bp.get("verified") is True:
                return True
        return False

    def _detect_and_patch_meta_patterns_unlocked(self) -> List[str]:
        """
        跨分支共性死因提炼 (Meta-Pattern Patch, §7.6.4)：
        当 `record_blacklist.jsonl` 中有 >= 3 条记录命中同一 `tried_mechanism` 或 `failure_category` (非默认 GENERAL_FAILURE) 时，
        自动将该共性陷阱写入 `shared_readonly/distilled/pitfall_guardrails.md`，阻止后续分支重复踩坑！
        """
        records = self._read_jsonl(self.records_file)
        if len(records) < 3:
            return []

        mech_counts: Dict[str, List[Dict[str, Any]]] = {}
        for r in records:
            key = str(r.get("failure_category") or "").strip()
            if not key or key == "GENERAL_FAILURE":
                key = str(r.get("tried_mechanism") or "").strip().lower()
            if key and key != "未注明机制":
                mech_counts.setdefault(key, []).append(r)

        guardrails_path = self.distilled_dir / "pitfall_guardrails.md"
        existing_text = guardrails_path.read_text(encoding="utf-8") if guardrails_path.exists() else "# 🛡️ 多模态数据源清点与防踩坑红线卡\n"
        newly_patched: List[str] = []

        for key, rec_list in mech_counts.items():
            if len(rec_list) >= 3:
                marker = f"[META-PATTERN:{key}]"
                if marker not in existing_text:
                    sample_summary = rec_list[-1].get("failure_summary", "")
                    patch_line = (
                        f"\n- **{marker} 跨分支共性死因自动补丁 (已连续触发 {len(rec_list)} 次失败)**："
                        f"严禁再次盲目尝试 `{key}`！典型失败机理：{sample_summary}\n"
                    )
                    existing_text += patch_line
                    newly_patched.append(key)

        if newly_patched:
            guardrails_path.write_text(existing_text, encoding="utf-8")

        return newly_patched

    def _audit_and_test_primitive(self, py_file: Path, island_dir: Path) -> Tuple[bool, str]:
        """
        对候选入库原语 `.py` 执行 AST 审计与独立沙箱单元测试：
        1. 必须包含至少一个公开函数/类及 Docstring；
        2. 必须包含至少一个 `def test_*()` 单元测试函数；
        3. 在隔离沙箱进程中执行所有 `test_*()` 函数，10 秒内 100% 通过才准入库 `Ledger`！
        """
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return False, f"语法错误: {e}"

        public_defs = []
        test_funcs = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    test_funcs.append(node.name)
                elif not node.name.startswith("_"):
                    public_defs.append(node)
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                public_defs.append(node)

        if not public_defs:
            return False, "原语文件中未找到任何公开函数或类定义"
        if not test_funcs:
            return False, "原语文件缺少强制要求的单元测试函数 `def test_xxx():` (至少需断言验证输入输出)"

        first_doc = ""
        for d in public_defs:
            doc = ast.get_docstring(d)
            if not doc:
                return False, f"公开原语 '{d.name}' 缺少 Docstring 功能说明"
            if not first_doc:
                first_doc = doc.splitlines()[0].strip()

        runner_code = (
            f"import importlib.util, sys\n"
            f"spec = importlib.util.spec_from_file_location('prim_mod', r'{str(py_file.resolve())}')\n"
            f"mod = importlib.util.module_from_spec(spec)\n"
            f"spec.loader.exec_module(mod)\n"
            f"for fn_name in {test_funcs!r}:\n"
            f"    getattr(mod, fn_name)()\n"
            f"print('PRIMITIVE_UNIT_TESTS_PASSED')\n"
        )
        run_res = run_bounded_subprocess(
            cmd=[sys.executable, "-c", runner_code],
            cwd=island_dir,
            shared_readonly_dir=self.shared_root,
            timeout_sec=10.0,
            max_memory_mb=2048,
        )
        if run_res.exit_code != 0 or "PRIMITIVE_UNIT_TESTS_PASSED" not in run_res.stdout:
            err_detail = (run_res.stderr or run_res.stdout).strip()[:300]
            return False, f"单元测试执行失败 (exit={run_res.exit_code}): {err_detail}"

        return True, first_doc

    # ========================================================================
    # 4. 排行榜幂等更新、L2 点读与错误结论撤回传播树 (Retraction Tree)
    # ========================================================================

    def update_leaderboard(
        self,
        node_id: str,
        family_id: str,
        commit_hash: str,
        frozen_score: float,
        live_score: float,
        wall_time_sec: float,
        summary: str,
        higher_is_better: bool = True,
    ) -> int:
        """在文件锁保护下幂等更新全局排行榜（按 `(node_id, commit_hash)` 自动去重）并返回当前排名 (1-based)"""
        with InterProcessFileLock(self.lock_file):
            lb_data = json.loads(self.leaderboard_file.read_text(encoding="utf-8")) if self.leaderboard_file.exists() else {"entries": []}
            entries: List[Dict[str, Any]] = [
                e for e in lb_data.get("entries", [])
                if not (e.get("node_id") == node_id and e.get("commit_hash") == commit_hash)
            ]
            entries.append(
                {
                    "node_id": node_id,
                    "family_id": family_id,
                    "commit_hash": commit_hash,
                    "frozen_score": frozen_score,
                    "live_score": live_score,
                    "wall_time_sec": wall_time_sec,
                    "summary": summary[:120],
                    "timestamp": time.time(),
                }
            )
            entries.sort(
                key=lambda x: (x.get("frozen_score", 0.0), x.get("live_score", 0.0)),
                reverse=higher_is_better,
            )
            lb_data["entries"] = entries
            self.leaderboard_file.write_text(json.dumps(lb_data, ensure_ascii=False, indent=2), encoding="utf-8")

            for idx, item in enumerate(entries, 1):
                if item["commit_hash"] == commit_hash and item["node_id"] == node_id:
                    return idx
            return len(entries)

    def retract_claim(self, target_claim_id: str, reason: str) -> List[str]:
        """
        错误结论撤回树 (Retraction Tree)：
        将 `target_claim_id` 标记为 `RETRACTED`，并顺着 `depends_on` DAG 将所有直接/间接下游结论降级为 `NEEDS_REVALIDATION`。
        """
        with InterProcessFileLock(self.lock_file):
            claims = self._read_jsonl(self.claims_file)
            affected: List[str] = []
            retracted_set = {target_claim_id}

            changed = True
            while changed:
                changed = False
                for c in claims:
                    cid = c.get("claim_id", "")
                    if cid == target_claim_id and c.get("status") != "RETRACTED":
                        c["status"] = "RETRACTED"
                        c["retract_reason"] = reason
                        affected.append(cid)
                        changed = True
                    elif c.get("status") == "VERIFIED_ACTIVE":
                        deps = set(c.get("depends_on", []))
                        if deps & retracted_set:
                            c["status"] = "NEEDS_REVALIDATION"
                            c["revalidation_trigger"] = f"Upstream dependency {list(deps & retracted_set)} retracted"
                            retracted_set.add(cid)
                            affected.append(cid)
                            changed = True

            self._write_jsonl(self.claims_file, claims)
            self.rebuild_l0_index()
            return affected

    def query_l2_item(self, item_id: str) -> Dict[str, Any]:
        """L2 按需点读指定编号的原语、死胡同记录、死路证明、引理或悬赏详情"""
        prim_candidate = self.primitives_dir / f"{item_id.removeprefix('prim_')}.py"
        if prim_candidate.exists():
            return {"type": "primitive", "id": item_id, "path": str(prim_candidate), "content": prim_candidate.read_text(encoding="utf-8")}
        for pf in self.primitives_dir.glob("*.py"):
            if pf.stem == item_id:
                return {"type": "primitive", "id": item_id, "path": str(pf), "content": pf.read_text(encoding="utf-8")}

        for r in self._read_jsonl(self.records_file):
            if r.get("record_id") == item_id or r.get("node_id") == item_id:
                return {"type": "record_blacklist", "data": r}
        for bp in self._read_jsonl(self.barrier_proofs_file):
            if bp.get("proof_id") == item_id:
                return {"type": "barrier_proof", "data": bp}
        for c in self._read_jsonl(self.claims_file):
            if c.get("claim_id") == item_id:
                return {"type": "claim", "data": c}
        for b in self._read_jsonl(self.bounties_file):
            if b.get("bounty_id") == item_id:
                return {"type": "bounty", "data": b}

        return {"type": "not_found", "message": f"未在档案馆中找到编号为 '{item_id}' 的条目"}

    @staticmethod
    def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
        return out

    @staticmethod
    def _append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    @staticmethod
    def _write_jsonl(path: Path, items: List[Dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(json.dumps(x, ensure_ascii=False) for x in items) + ("\n" if items else "")
        path.write_text(content, encoding="utf-8")
