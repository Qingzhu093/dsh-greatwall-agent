"""
Great Wall Agent V4.2 — Unattended Campaign Orchestration Engine.
严格对齐《15_长城Agent_V4无人值守架构与沙箱工程实战规范.md》全章节机制：
1. Phase 0 开局静态数据探针 (`_run_eda_probe`, §1.3) + M 候选基线实跑排序择优固化 `s_0` (`lock_opening_distillation`, §2.3)；
2. 跨进程文件锁 (`InterProcessFileLock`) + 预写式事务日志 (`wal.jsonl`) 崩溃自愈对齐 (§6.3)；
3. 阶段感知评测压力调节器 (`compute_campaign_stage`, Stage 0~3, §7.2.2)；
4. 60 步导师深挖承诺锁 (`check_or_abandon_lineage`, 除非提交沙箱证实的 `BarrierProof` 否则禁止未满 60 步提前弃坑, §7.6.1)；
5. 双层回滚与分叉算子：原地软清栈 (`soft_flush_slot`, Soft Flush) 与退回祖先硬分叉 (`hard_fork_ancestor`, Ancestor Hard Fork, §6.2.2)；
6. 60 步原位 3 轮内省室契约持久化 (`submit_reflection_record`, `.kernel_vault/reflections/*.json`, §7.6.3 & §8.1 #12)；
7. 跨分支差分互测 (`run_differential_test`, §7.4) 与评测集错题热勘误追溯重算 (`deprecate_errata_case`, §7.3.2)；
8. 终局防吹牛数字硬绑定审计与五件套交付信封编译 (`compile_final_delivery`, §8.3.2)。
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .archive import LightweightArchive
from .evaluator import DEFAULT_TEXTBOOK_COMMONSENSE, ASTCodeInspector, IsolatedEvaluator
from .sandbox import CleanRoomSandbox, InterProcessFileLock, SandboxPathJail, force_cleanup_directory


class GreatWallEngine:
    """
    长城 Agent V4.2 顶层编排引擎：
    - 管理 `.kernel_vault/state_graph.json`、`wal.jsonl` 与 `.kernel_vault/reflections/`；
    - 驱动 Phase 0 开局消歧、EDA 静态探针与知识蒸馏四件套固化（支持 M 候选基线竞技选优）；
    - 管理并发槽位 (Slots)、原地软清栈 (Soft Flush)、祖先硬分叉 (Hard Fork)、60 步深挖锁与原位 3 轮内省室；
    - 执行终局防吹牛数字硬绑定与五件套交付信封打包。
    """

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.sandbox = CleanRoomSandbox(self.workspace_root)
        self.archive = LightweightArchive(self.sandbox.shared_readonly_dir)
        self.evaluator = IsolatedEvaluator(self.sandbox.vault_dir, self.sandbox.shared_readonly_dir)

        self.engine_lock_file = self.sandbox.vault_dir / "engine.lock"
        self.state_file = self.sandbox.vault_dir / "state_graph.json"
        self.wal_file = self.sandbox.vault_dir / "wal.jsonl"
        self.reflections_dir = self.sandbox.vault_dir / "reflections"
        self.distilled_dir = self.sandbox.shared_readonly_dir / "distilled"
        self.reflections_dir.mkdir(parents=True, exist_ok=True)
        self.distilled_dir.mkdir(parents=True, exist_ok=True)

    # ========================================================================
    # 1. 状态持久化、WAL 预写日志与阶段感知压力调节器 (Pressure Modulator)
    # ========================================================================

    def _append_wal(self, event_type: str, payload: Dict[str, Any]) -> int:
        entry = {
            "ts": time.time(),
            "event": event_type,
            "payload": payload,
        }
        with self.wal_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return int(entry["ts"] * 1000)

    def load_state(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {
                "initialized": False,
                "task_id": "",
                "domain_type": "ALGO_COMPETITION",
                "primary_metric": "score",
                "higher_is_better": True,
                "anchor_s0_commit": "",
                "anchor_s0_score": 0.0,
                "total_steps_executed": 0,
                "total_step_budget": 240,
                "max_concurrent_slots": 4,
                "active_slots": {},
                "lineages": {},
                "pending_proposals": [],
                "reflections_completed": 0,
            }
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        # 幂等自愈检查：若 active_slots 中的物理目录在崩溃后已丢失，但快照尚存，自动根据 base_commit 重建孤岛目录
        active_slots = state.get("active_slots", {})
        for slot_id, sinfo in list(active_slots.items()):
            ipath = Path(sinfo.get("island_path", ""))
            if sinfo.get("base_commit") and not ipath.exists():
                self.sandbox.checkout_clean_island(
                    commit_hash=sinfo["base_commit"],
                    slot_dir_name=slot_id,
                    scoped_brief_md="",
                )
        return state

    def save_state(self, state: Dict[str, Any]) -> None:
        tmp_path = self.state_file.with_suffix(f".{time.time_ns()}.tmp")
        tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.state_file)

    @staticmethod
    def compute_campaign_stage(total_steps_executed: int, total_step_budget: int = 240) -> Dict[str, Any]:
        r"""
        阶段感知压力调节器 (Pressure Modulator, §7.2.2)：
        根据当前已消耗步数占总预算比例 $p \in [0, 1]$，动态调整评测准入严苛度与探索策略。
        """
        budget = max(1, total_step_budget)
        progress = round(min(1.0, total_steps_executed / budget), 4)
        if progress < 0.10:
            stage = "STAGE_0_DISTILLATION"
            policy = "完成开局静态数据探针 (EDA) 与多候选零号基线 s_0 实跑锁定。"
        elif progress < 0.45:
            stage = "STAGE_1_DIVERGENT_EXPLORATION"
            policy = "鼓励多正交方法族并行发散探索，允许 NICHE_CHAMPION 局部优势解保留。"
        elif progress < 0.85:
            stage = "STAGE_2_CONVERGENT_REFINEMENT"
            policy = "收敛期：优先调度跨血统原语嫁接 (GRAFT) 与瓶颈代码块微创深挖，严审结构改动率。"
        else:
            stage = "STAGE_3_CONSOLIDATION_FREEZE"
            policy = "终局冲刺冻结期：禁止开辟未经验证的全新野生方法族，集中算力做融合验证与交付打包。"
        return {
            "stage": stage,
            "budget_progress": progress,
            "steps_executed": total_steps_executed,
            "total_step_budget": budget,
            "stage_policy": policy,
        }

    # ========================================================================
    # 2. Phase 0：工作区初始化、确定性 EDA 探针与开局先蒸馏固化 (§1.3 & §2.3)
    # ========================================================================

    def _run_eda_probe(self, datasets_dir: Path) -> Dict[str, Any]:
        """
        确定性开局数据探针 (EDA Grounding Probe, §1.3)：
        自动扫描 `shared_readonly/datasets_public/` 下的所有数据文件，
        提取行列规模、字段名、缺失率、数值极值等客观统计量，彻底消灭题面幻觉。
        """
        modalities_summary: List[Dict[str, Any]] = []
        for fpath in sorted(datasets_dir.rglob("*")):
            if not fpath.is_file():
                continue
            rel_name = fpath.relative_to(datasets_dir).as_posix()
            fsize = fpath.stat().st_size
            ext = fpath.suffix.lower()
            info: Dict[str, Any] = {
                "file": rel_name,
                "size_bytes": fsize,
                "format": ext.lstrip(".") or "raw",
            }
            try:
                if ext in (".csv", ".tsv"):
                    delim = "\t" if ext == ".tsv" else ","
                    with fpath.open("r", encoding="utf-8", errors="replace", newline="") as f:
                        reader = csv.reader(f, delimiter=delim)
                        headers = next(reader, [])
                        row_count = 0
                        missing_counts = [0] * len(headers)
                        for row in reader:
                            row_count += 1
                            for idx in range(min(len(headers), len(row))):
                                if row[idx].strip() in ("", "NA", "NaN", "null", "None"):
                                    missing_counts[idx] += 1
                        info["columns"] = headers[:50]
                        info["num_columns"] = len(headers)
                        info["num_rows"] = row_count
                        if row_count > 0 and headers:
                            info["missing_rates"] = {
                                headers[i]: round(missing_counts[i] / row_count, 4)
                                for i in range(min(20, len(headers)))
                                if missing_counts[i] > 0
                            }
                elif ext == ".json":
                    data = json.loads(fpath.read_text(encoding="utf-8", errors="replace"))
                    if isinstance(data, list):
                        info["num_records"] = len(data)
                        if data and isinstance(data[0], dict):
                            info["sample_keys"] = list(data[0].keys())[:30]
                    elif isinstance(data, dict):
                        info["top_keys"] = list(data.keys())[:30]
                else:
                    lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
                    info["num_lines"] = len(lines)
                    info["head_preview"] = lines[:3]
            except Exception as e:
                info["probe_warning"] = str(e)
            modalities_summary.append(info)

        probe_report = {
            "probed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_files": len(modalities_summary),
            "modalities": modalities_summary,
        }
        (self.distilled_dir / "eda_probe_report.json").write_text(
            json.dumps(probe_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return probe_report

    def init_campaign(
        self,
        task_id: str,
        task_description: str,
        domain_type: str = "ALGO_COMPETITION",
        primary_metric: str = "score",
        higher_is_better: bool = True,
        max_concurrent_slots: int = 4,
        total_step_budget: int = 240,
        resolved_ambiguities: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        初始化长程无人值守工作区，执行开局数据静态探针 (EDA Grounding)，
        并锁死 `shared_readonly/task_config.yaml` (杜绝盘中分裂 A/~A 歧义分支)。
        """
        with InterProcessFileLock(self.engine_lock_file):
            self._append_wal("INIT_CAMPAIGN", {"task_id": task_id, "domain_type": domain_type})

            datasets_dir = self.sandbox.shared_readonly_dir / "datasets_public"
            datasets_dir.mkdir(parents=True, exist_ok=True)
            eda_report = self._run_eda_probe(datasets_dir)
            discovered_files = [m["file"] for m in eda_report["modalities"]]

            task_contract = {
                "task_id": task_id,
                "domain_type": domain_type,
                "task_description": task_description,
                "evaluation_protocol": {
                    "primary_metric": primary_metric,
                    "higher_is_better": higher_is_better,
                    "anchor_baseline_s0_score": 0.0,
                },
                "data_completeness_inventory": discovered_files,
                "eda_probe_summary": eda_report,
                "resolved_ambiguities": resolved_ambiguities or [],
                "locked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            task_cfg_path = self.sandbox.shared_readonly_dir / "task_config.yaml"
            task_cfg_path.write_text(json.dumps(task_contract, ensure_ascii=False, indent=2), encoding="utf-8")

            state = self.load_state()
            state.update(
                {
                    "initialized": True,
                    "task_id": task_id,
                    "domain_type": domain_type,
                    "primary_metric": primary_metric,
                    "higher_is_better": higher_is_better,
                    "max_concurrent_slots": max_concurrent_slots,
                    "total_step_budget": total_step_budget,
                    "data_inventory": discovered_files,
                    "created_at": time.time(),
                }
            )
            self.save_state(state)
            self.archive.rebuild_l0_index()

            return {
                "status": "OK",
                "workspace_root": str(self.workspace_root),
                "task_config_path": str(task_cfg_path),
                "discovered_data_modalities": discovered_files,
                "eda_probe_report": eda_report,
                "next_step": "请运行 Phase 0 开局知识蒸馏，然后调用 gw_lock_distillation 固化 SOTA 锚点卡与零号强基线 s_0。",
            }

    def lock_opening_distillation(
        self,
        orthogonal_families: List[Dict[str, Any]],
        obsolete_blacklist: Optional[List[str]] = None,
        must_reuse_libraries: Optional[List[str]] = None,
        pitfall_guardrails: Optional[List[str]] = None,
        anchor_baseline_code: str = "",
        candidate_baselines: Optional[List[Dict[str, str]]] = None,
        commonsense_blacklist: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        r"""
        固化 Phase 0 开局蒸馏四件套，并在沙箱中实跑验分铸造【零号强基线 s_0】(§2.3)：
        - 支持传入单个 `anchor_baseline_code` 或多个候选基线 `candidate_baselines: [{"name": "...", "code": "..."}]`；
        - 当传入 M 个候选基线时，在隔离沙箱中逐一实跑评测，按验证分 $h(s_{(1)}) \ge \dots \ge h(s_{(M)})$ 排序择优（满足 $h(s_{cand}) > h(s_0) + \epsilon_{min}$ 贪心晋级），锁入 `anchor_baseline.py`！
        """
        with InterProcessFileLock(self.engine_lock_file):
            state = self.load_state()
            if not state.get("initialized"):
                raise RuntimeError("工作区尚未初始化，请先调用 gw_init_campaign！")

            higher_is_better = bool(state.get("higher_is_better", True))

            sota_pack = {
                "obsolete_familiarity_blacklist": obsolete_blacklist or [
                    "LogisticRegression / Ridge as final model",
                    "ResNet18 / ResNet50 (2015) without modern ViT/ConvNeXt comparison",
                    "Unvectorized triple Python for-loops on N > 2000",
                ],
                "trivial_commonsense_blacklist": commonsense_blacklist or DEFAULT_TEXTBOOK_COMMONSENSE,
                "orthogonal_families": orthogonal_families,
            }
            (self.distilled_dir / "sota_anchors.json").write_text(
                json.dumps(sota_pack, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            build_vs_buy = {
                "must_reuse_infrastructure": must_reuse_libraries or [
                    "sklearn.model_selection.(StratifiedKFold | GroupKFold | TimeSeriesSplit)",
                    "scipy.spatial.cKDTree / scipy.spatial.distance.cdist",
                    "archive.ledger.primitives.*",
                ],
                "encouraged_custom_operator_zones": [f.get("custom_zone", "核心瓶颈算子与领域特征块") for f in orthogonal_families],
            }
            (self.distilled_dir / "build_vs_buy_contract.json").write_text(
                json.dumps(build_vs_buy, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            guardrails_lines = ["# 🛡️ 多模态数据源清点与防踩坑红线卡 (Pitfall Guardrails)\n"]
            for idx, g in enumerate(pitfall_guardrails or [
                "一切特征归一化与缺失值统计量填充必须在每个 CV 折的 train_idx 内部独立 fit，严禁全局 fit_transform！",
                "严禁在代码中硬编码测试集算例编号或静态预测数组！",
            ], 1):
                guardrails_lines.append(f"{idx}. {g}")
            (self.distilled_dir / "pitfall_guardrails.md").write_text("\n".join(guardrails_lines) + "\n", encoding="utf-8")

            # 组装待竞技的候选基线列表 {s_init^1, ..., s_init^M}
            candidates_to_run: List[Dict[str, str]] = []
            if candidate_baselines:
                for idx, c in enumerate(candidate_baselines, 1):
                    if isinstance(c, dict) and str(c.get("code", "")).strip():
                        candidates_to_run.append({
                            "name": str(c.get("name") or f"CAND_{idx:02d}"),
                            "code": str(c["code"]),
                        })
            if anchor_baseline_code.strip() and not candidates_to_run:
                candidates_to_run.append({"name": "ANCHOR_PRIMARY", "code": anchor_baseline_code})

            s0_commit = "GENESIS_S0"
            s0_score = 0.0
            s0_eval_receipt: Dict[str, Any] = {}
            candidate_tournament_log: List[Dict[str, Any]] = []
            winning_code = anchor_baseline_code

            if candidates_to_run:
                best_score_val: Optional[float] = None
                for idx, cand in enumerate(candidates_to_run, 1):
                    cname = cand["name"]
                    ccode = cand["code"]
                    s0_island = self.sandbox.worktrees_dir / f"_anchor_s0_cand_{idx:02d}"
                    if s0_island.exists():
                        force_cleanup_directory(s0_island, self.sandbox.graveyard_dir)
                    (s0_island / "src").mkdir(parents=True, exist_ok=True)
                    (s0_island / "legacy_out").mkdir(parents=True, exist_ok=True)
                    (s0_island / "src" / "main.py").write_text(ccode, encoding="utf-8")

                    c_commit = self.sandbox.store_snapshot(s0_island, parent_commit="GENESIS", message=f"Phase 0 Candidate {cname}")
                    c_receipt = self.evaluator.evaluate_island(
                        island_dir=s0_island,
                        node_id=f"S0_{cname}",
                        commit_hash=c_commit,
                        entry_script="src/main.py",
                        higher_is_better=higher_is_better,
                    )
                    force_cleanup_directory(s0_island, self.sandbox.graveyard_dir)

                    if "scores" in c_receipt:
                        c_score = float(c_receipt["scores"]["frozen_benchmark"])
                        is_better = (
                            best_score_val is None
                            or (higher_is_better and c_score > best_score_val + 1e-6)
                            or (not higher_is_better and c_score < best_score_val - 1e-6)
                        )
                        candidate_tournament_log.append({
                            "candidate_name": cname,
                            "commit_hash": c_commit,
                            "frozen_score": c_score,
                            "promoted_to_s0": is_better,
                        })
                        if is_better:
                            best_score_val = c_score
                            s0_score = c_score
                            s0_commit = c_commit
                            s0_eval_receipt = c_receipt
                            winning_code = ccode
                    else:
                        candidate_tournament_log.append({
                            "candidate_name": cname,
                            "commit_hash": c_commit,
                            "status": c_receipt.get("status", "FAILED"),
                            "promoted_to_s0": False,
                        })

                if winning_code.strip():
                    (self.distilled_dir / "anchor_baseline.py").write_text(winning_code, encoding="utf-8")
                if "scores" in s0_eval_receipt:
                    self.archive.update_leaderboard(
                        node_id="ANCHOR_S0",
                        family_id="ANCHOR_S0",
                        commit_hash=s0_commit,
                        frozen_score=s0_score,
                        live_score=float(s0_eval_receipt["scores"]["live_challenge"]),
                        wall_time_sec=float(s0_eval_receipt["resource_profile"]["wall_time_sec"]),
                        summary=f"Phase 0 开局蒸馏实跑选优固化的零号强基线 s_0 (共竞技 {len(candidates_to_run)} 个候选)",
                        higher_is_better=higher_is_better,
                    )

            # 初始化各正交方法族的谱系追踪 (Lineage BeliefState)
            lineages = state.setdefault("lineages", {})
            for fam in orthogonal_families:
                fid = fam.get("family_id", "FAM-01")
                lin_id = f"LIN-{fid}"
                lineages[lin_id] = {
                    "family_id": fid,
                    "family_name": fam.get("family_name", fid),
                    "lineage_id": lin_id,
                    "steps_invested": 0,
                    "last_reflected_step": 0,
                    "head_commit": s0_commit,
                    "best_score": s0_score,
                    "status": "ACTIVE_DEEPENING",
                }

            state["anchor_s0_commit"] = s0_commit
            state["anchor_s0_score"] = s0_score
            self.save_state(state)
            self.archive.rebuild_l0_index()
            self._append_wal("LOCK_DISTILLATION", {"s0_commit": s0_commit, "s0_score": s0_score, "candidates": len(candidates_to_run)})

            return {
                "status": "OK",
                "anchor_s0_commit": s0_commit,
                "anchor_s0_score": s0_score,
                "candidate_tournament_log": candidate_tournament_log,
                "registered_families": [f.get("family_id") for f in orthogonal_families],
                "s0_evaluation": s0_eval_receipt,
            }

    # ========================================================================
    # 3. 并发槽位分配、代码块微创手术、沙箱评测与五件套遗产交卷
    # ========================================================================

    def allocate_exploration_slot(
        self,
        family_id: str,
        targeted_code_block: str,
        hypothesis: str,
        parent_commit: Optional[str] = None,
        step_budget: int = 25,
        is_unbound_junior: bool = False,
    ) -> Dict[str, Any]:
        """
        分配一个无 `.git` 的清洁室孤岛槽位 (`worktrees/slot_xx_node_yy/`)，
        自动检查该正交方法族是否已被 `BarrierProof` 证伪封禁，检出基底快照并注入 `scoped_brief.md`。
        """
        with InterProcessFileLock(self.engine_lock_file):
            state = self.load_state()
            if self.archive.has_verified_barrier_for_family(family_id):
                return {
                    "status": "BLOCKED_BY_BARRIER_PROOF",
                    "family_id": family_id,
                    "message": f"正交方法族 '{family_id}' 已有经沙箱反例脚本证实的死路证明 (BarrierProof)，调度器拒绝在该死胡同继续分配算力！",
                }

            active_slots: Dict[str, Any] = state.setdefault("active_slots", {})
            max_slots = int(state.get("max_concurrent_slots", 4))
            if len(active_slots) >= max_slots:
                return {
                    "status": "SLOTS_FULL",
                    "message": f"当前活跃槽位已满 ({len(active_slots)}/{max_slots})，请先完成现有节点的评测与遗产归档！",
                    "active_slots": list(active_slots.keys()),
                }

            node_seq = int(state.get("node_counter", 0)) + 1
            state["node_counter"] = node_seq
            node_id = f"NODE-{node_seq:03d}"
            slot_id = f"slot_{len(active_slots) + 1:02d}_{node_id.lower()}"
            lineage_id = "UNBOUND_JUNIOR" if is_unbound_junior else f"LIN-{family_id}"

            lineages = state.setdefault("lineages", {})
            lin_info = lineages.get(lineage_id, {})
            base_commit = parent_commit or lin_info.get("head_commit") or state.get("anchor_s0_commit") or "GENESIS_S0"

            brief_md = self.archive.build_scoped_l1_brief(
                node_id=node_id,
                slot_id=slot_id,
                family_id="GLOBAL" if is_unbound_junior else family_id,
                lineage_id=lineage_id,
                parent_commit=base_commit,
                targeted_code_block=targeted_code_block,
                hypothesis=hypothesis,
                step_budget=step_budget,
            )

            island_dir = self.sandbox.checkout_clean_island(
                commit_hash=base_commit,
                slot_dir_name=slot_id,
                scoped_brief_md=brief_md,
            )

            slot_record = {
                "slot_id": slot_id,
                "node_id": node_id,
                "family_id": family_id,
                "lineage_id": lineage_id,
                "base_commit": base_commit,
                "targeted_code_block": targeted_code_block,
                "hypothesis": hypothesis,
                "island_path": str(island_dir),
                "step_budget": step_budget,
                "allocated_at": time.time(),
            }
            active_slots[slot_id] = slot_record
            self.save_state(state)
            self._append_wal("ALLOCATE_SLOT", slot_record)

            return {
                "status": "OK",
                "slot_id": slot_id,
                "node_id": node_id,
                "lineage_id": lineage_id,
                "base_commit": base_commit,
                "island_path": str(island_dir),
                "scoped_brief_path": str(island_dir / "scoped_brief.md"),
                "campaign_stage": self.compute_campaign_stage(
                    int(state.get("total_steps_executed", 0)),
                    int(state.get("total_step_budget", 240)),
                ),
            }

    def surgical_replace_in_slot(
        self,
        slot_id: str,
        target_block_name: str,
        new_block_code: str,
        rel_script_path: str = "src/main.py",
    ) -> Dict[str, Any]:
        """在指定槽位的清洁室孤岛内执行 MLE-STAR 式局部代码块微创热插拔替换（支持顶层函数/类及 ClassName.method）"""
        state = self.load_state()
        slot_info = state.get("active_slots", {}).get(slot_id)
        if not slot_info:
            return {"status": "ERROR", "message": f"找不到活跃槽位: {slot_id}"}

        island_dir = Path(slot_info["island_path"])
        jail = SandboxPathJail(island_dir, self.sandbox.shared_readonly_dir, slot_info.get("lineage_id", "GLOBAL"))
        safe_script_path = jail.validate_write(rel_script_path)

        ok, msg = self.sandbox.surgical_replace_block(safe_script_path, target_block_name, new_block_code)
        if ok:
            # 自动刷新 legacy_out/diff.patch
            self.sandbox.generate_unified_diff(slot_info.get("base_commit", "GENESIS"), island_dir)
        return {
            "status": "OK" if ok else "ERROR",
            "slot_id": slot_id,
            "target_block_name": target_block_name,
            "script_path": str(safe_script_path),
            "message": msg,
        }

    def evaluate_slot(
        self,
        slot_id: str,
        entry_script: str = "src/main.py",
        claimed_swept_variables: Optional[List[str]] = None,
        operator_description: str = "",
        timeout_sec: float = 120.0,
        enforce_data_completeness: bool = False,
    ) -> Dict[str, Any]:
        """
        对指定槽位的代码生成快照与 `diff.patch`，并执行跨进程防作弊评测，签发带 HMAC 签名的 `legacy_out/metrics_receipt.json`
        """
        with InterProcessFileLock(self.engine_lock_file):
            state = self.load_state()
            slot_info = state.get("active_slots", {}).get(slot_id)
            if not slot_info:
                return {"status": "ERROR", "message": f"找不到活跃槽位: {slot_id}"}

            island_dir = Path(slot_info["island_path"])
            base_commit = slot_info.get("base_commit", "GENESIS")
            parent_snap_file = self.sandbox.snapshots_dir / base_commit / "files" / entry_script
            parent_code = parent_snap_file.read_text(encoding="utf-8") if parent_snap_file.exists() else ""

            # 生成统一补丁 legacy_out/diff.patch
            self.sandbox.generate_unified_diff(base_commit, island_dir)

            commit_hash = self.sandbox.store_snapshot(
                island_dir, parent_commit=base_commit, message=f"Eval {slot_info['node_id']}: {slot_info.get('hypothesis', '')}"
            )
            slot_info["latest_commit"] = commit_hash
            self.save_state(state)

        receipt = self.evaluator.evaluate_island(
            island_dir=island_dir,
            node_id=slot_info["node_id"],
            commit_hash=commit_hash,
            entry_script=entry_script,
            parent_code=parent_code,
            anchor_s0_score=float(state.get("anchor_s0_score", 0.0)),
            higher_is_better=bool(state.get("higher_is_better", True)),
            timeout_sec=timeout_sec,
            claimed_swept_variables=claimed_swept_variables,
            operator_description=operator_description,
            enforce_data_completeness=enforce_data_completeness,
        )
        self._append_wal("EVALUATE_SLOT", {"slot_id": slot_id, "commit_hash": commit_hash, "triage": receipt.get("triage_tier")})
        return receipt

    def submit_legacy_and_release_slot(
        self,
        slot_id: str,
        steps_consumed: int = 15,
    ) -> Dict[str, Any]:
        """
        验收探索节点留下的【五件套遗产包】，校验 HMAC 成绩单签名，
        统计跨血统原语真实引用次数，更新档案馆与谱系步数计数（若满 60 步自动触发原位 3 轮内省室信号），并调用五步墓碑算法回收孤岛目录。
        """
        with InterProcessFileLock(self.engine_lock_file):
            state = self.load_state()
            active_slots = state.get("active_slots", {})
            slot_info = active_slots.get(slot_id)
            if not slot_info:
                return {"status": "ERROR", "message": f"找不到活跃槽位: {slot_id}"}

            island_dir = Path(slot_info["island_path"])
            node_id = slot_info["node_id"]
            family_id = slot_info["family_id"]
            lineage_id = slot_info["lineage_id"]
            base_commit = slot_info.get("base_commit", "GENESIS")

            # 确保 legacy_out/diff.patch 存在
            self.sandbox.generate_unified_diff(base_commit, island_dir)
            commit_hash = slot_info.get("latest_commit") or self.sandbox.store_snapshot(island_dir, base_commit, f"Final {node_id}")

            # 1. 校验五件套遗产包并入库
            val_res = self.archive.validate_and_admit_legacy(
                island_dir=island_dir,
                node_id=node_id,
                family_id=family_id,
                lineage_id=lineage_id,
                commit_hash=commit_hash,
            )
            if not val_res.ok:
                return {
                    "status": "LEGACY_REJECTED",
                    "slot_id": slot_id,
                    "errors": val_res.errors,
                    "warnings": val_res.warnings,
                    "message": "五件套遗产包校验未通过，槽位拒绝释放！请按 errors 列表补齐文件后重新提交。",
                }

            # 2. 校验成绩单 HMAC 签名并更新排行榜
            receipt_path = island_dir / "legacy_out" / "metrics_receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if not self.evaluator.verify_receipt_signature(receipt):
                return {
                    "status": "FORGED_RECEIPT_DETECTED",
                    "slot_id": slot_id,
                    "message": "安全警报：metrics_receipt.json 的 HMAC-SHA256 签名验证失败，严禁手工伪造成绩单！",
                }

            frozen_score = float(receipt["scores"]["frozen_benchmark"])
            live_score = float(receipt["scores"]["live_challenge"])
            triage_tier = receipt.get("triage_tier", "DEAD_END_ARCHIVE")

            # 若本节点取得有效提分 (PARETO_PROMOTE / NICHE_CHAMPION)，为所引用的跨血统原语累加有效引用数 (§3.2.2)
            credited_primitives: List[str] = []
            if triage_tier in ("PARETO_PROMOTE", "NICHE_CHAMPION"):
                imported_prims = receipt.get("ast_audit", {}).get("imported_archive_primitives", [])
                credited_primitives = self.archive.increment_primitive_citations(
                    imported_primitive_stems=imported_prims,
                    caller_lineage_id=lineage_id,
                    caller_node_id=node_id,
                )

            rank = self.archive.update_leaderboard(
                node_id=node_id,
                family_id=family_id,
                commit_hash=commit_hash,
                frozen_score=frozen_score,
                live_score=live_score,
                wall_time_sec=float(receipt["resource_profile"]["wall_time_sec"]),
                summary=slot_info.get("hypothesis", ""),
                higher_is_better=bool(state.get("higher_is_better", True)),
            )

            # 3. 读取遗嘱提案排入调度器队列
            will_path = island_dir / "legacy_out" / "last_will_proposals.json"
            will_data = json.loads(will_path.read_text(encoding="utf-8"))
            proposals = will_data if isinstance(will_data, list) else will_data.get("proposals", [])
            pending_queue: List[Dict[str, Any]] = state.setdefault("pending_proposals", [])
            for p in proposals:
                p["from_node_id"] = node_id
                p["family_id"] = family_id
                p["parent_commit"] = commit_hash
                pending_queue.append(p)
            pending_queue.sort(key=lambda x: float(x.get("priority_score", 0.5)), reverse=True)

            # 4. 更新谱系步数与最优解指针，检查是否触发 60 步原位内省室 (Station Reflection Chamber)
            state["total_steps_executed"] = int(state.get("total_steps_executed", 0)) + steps_consumed
            lineages = state.setdefault("lineages", {})
            lin_state = lineages.setdefault(
                lineage_id,
                {"family_id": family_id, "lineage_id": lineage_id, "steps_invested": 0, "last_reflected_step": 0, "head_commit": commit_hash, "best_score": frozen_score},
            )
            lin_state["steps_invested"] = int(lin_state.get("steps_invested", 0)) + steps_consumed
            if val_res.admitted_barrier_proofs:
                lin_state["status"] = "TERMINATED_BY_BARRIER_PROOF"
            elif triage_tier == "PARETO_PROMOTE":
                lin_state["head_commit"] = commit_hash
                lin_state["best_score"] = frozen_score
                lin_state["bonus_lease_steps"] = int(lin_state.get("bonus_lease_steps", 0)) + 25

            needs_reflection_chamber = (
                lin_state["steps_invested"] >= 60
                and int(lin_state.get("last_reflected_step", 0)) + 60 <= lin_state["steps_invested"]
            )

            # 5. 五步墓碑算法安全回收孤岛目录
            force_cleanup_directory(island_dir, self.sandbox.graveyard_dir)
            active_slots.pop(slot_id, None)
            self.save_state(state)
            self.archive.rebuild_l0_index()
            self._append_wal("RELEASE_SLOT", {"slot_id": slot_id, "node_id": node_id, "triage": triage_tier, "rank": rank})

            return {
                "status": "OK",
                "node_id": node_id,
                "commit_hash": commit_hash,
                "triage_tier": triage_tier,
                "leaderboard_rank": rank,
                "admitted_primitives": val_res.admitted_primitives,
                "admitted_claims": val_res.admitted_claims,
                "admitted_barrier_proofs": val_res.admitted_barrier_proofs,
                "credited_cross_lineage_primitives": credited_primitives,
                "meta_patterns_patched": val_res.meta_patterns_patched,
                "admitted_record_id": val_res.admitted_record_id,
                "lineage_steps_invested": lin_state["steps_invested"],
                "trigger_60_step_reflection_chamber": needs_reflection_chamber,
                "reflection_prompt_hint": (
                    "该谱系已累积满 60 步！请立即调用 gw_lineage_control (action='submit_reflection') 完成 Station 原位 3 轮内省室审计！"
                    if needs_reflection_chamber
                    else ""
                ),
            }

    # ========================================================================
    # 4. 双层上下文回滚算子 (Soft Flush & Ancestor Hard Fork)、60步深挖锁与原位内省室 (§6.2.2 & §7.6)
    # ========================================================================

    def soft_flush_slot(
        self,
        slot_id: str,
        failure_epitaph: str,
        new_targeted_block: Optional[str] = None,
        new_hypothesis: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        算子 A：原地软清栈 (`Soft Flush`, §6.2.2)：
        当探索节点在局部迭代中把代码改乱或连续报错时：
        1. 将失败原因写入 `record_blacklist.jsonl`；
        2. 丢弃当前孤岛未提交的脏改动，直接恢复至 `base_commit` 干净快照；
        3. 将 `failure_epitaph` 作为高亮红牌警告注入 `scoped_brief.md` 顶部，让节点以清爽状态重试！
        """
        with InterProcessFileLock(self.engine_lock_file):
            state = self.load_state()
            slot_info = state.get("active_slots", {}).get(slot_id)
            if not slot_info:
                return {"status": "ERROR", "message": f"找不到活跃槽位: {slot_id}"}

            base_commit = slot_info["base_commit"]
            family_id = slot_info["family_id"]
            lineage_id = slot_info["lineage_id"]
            node_id = slot_info["node_id"]
            target_block = new_targeted_block or slot_info["targeted_code_block"]
            hypothesis = new_hypothesis or slot_info["hypothesis"]

            # 记录此次软清栈死因到黑名单
            rec_id = f"REC-FLUSH-{int(time.time() * 1000) % 100000:05d}"
            self.archive._append_jsonl(
                self.archive.records_file,
                {
                    "record_id": rec_id,
                    "node_id": node_id,
                    "family_id": family_id,
                    "lineage_id": lineage_id,
                    "commit_hash": base_commit,
                    "tried_mechanism": f"SoftFlush on {target_block}",
                    "failure_category": "SOFT_FLUSH_ROLLBACK",
                    "failure_summary": failure_epitaph,
                    "timestamp": time.time(),
                },
            )

            brief_md = self.archive.build_scoped_l1_brief(
                node_id=node_id,
                slot_id=slot_id,
                family_id=family_id,
                lineage_id=lineage_id,
                parent_commit=base_commit,
                targeted_code_block=target_block,
                hypothesis=hypothesis,
                step_budget=int(slot_info.get("step_budget", 25)),
                soft_flush_warning=failure_epitaph,
            )

            island_dir = self.sandbox.checkout_clean_island(
                commit_hash=base_commit,
                slot_dir_name=slot_id,
                scoped_brief_md=brief_md,
            )
            slot_info["targeted_code_block"] = target_block
            slot_info["hypothesis"] = hypothesis
            slot_info["soft_flush_count"] = int(slot_info.get("soft_flush_count", 0)) + 1
            slot_info.pop("latest_commit", None)
            self.save_state(state)
            self._append_wal("SOFT_FLUSH_SLOT", {"slot_id": slot_id, "base_commit": base_commit, "record_id": rec_id})

            return {
                "status": "OK",
                "action": "SOFT_FLUSH",
                "slot_id": slot_id,
                "restored_commit": base_commit,
                "island_path": str(island_dir),
                "soft_flush_count": slot_info["soft_flush_count"],
                "message": f"已完成原地软清栈：脏代码已回滚至 {base_commit}，失败教训 ({rec_id}) 已置顶写入 scoped_brief.md。",
            }

    def hard_fork_ancestor(
        self,
        slot_id: str,
        ancestor_commit: Optional[str],
        new_family_id: str,
        new_targeted_block: str,
        new_hypothesis: str,
        abandon_reason: str = "",
    ) -> Dict[str, Any]:
        """
        算子 B：退回祖先硬分叉 (`Ancestor Hard Fork`, §6.2.2 & §7.6.1)：
        当一条技术路线陷入结构性死胡同时，退回更早期的祖先快照（或 `s_0`）开辟全新血统分支。
        **铁律检查**：若原方法族累积投入尚未满 60 步且未提交经沙箱证实的 `BarrierProof`，拒绝盲目弃坑打一枪换一个地方！
        """
        with InterProcessFileLock(self.engine_lock_file):
            state = self.load_state()
            slot_info = state.get("active_slots", {}).get(slot_id)
            if not slot_info:
                return {"status": "ERROR", "message": f"找不到活跃槽位: {slot_id}"}

            old_family_id = slot_info["family_id"]
            old_lineage_id = slot_info["lineage_id"]
            lin_state = state.get("lineages", {}).get(old_lineage_id, {})
            steps_invested = int(lin_state.get("steps_invested", 0))

            # 60 步导师深挖承诺门禁 (§7.6.1)
            if old_family_id != new_family_id and steps_invested < 60:
                if not self.archive.has_verified_barrier_for_family(old_family_id):
                    return {
                        "status": "COMMITMENT_LOCK_ACTIVE",
                        "family_id": old_family_id,
                        "steps_invested": steps_invested,
                        "required_steps": 60,
                        "message": (
                            f"【60 步导师深挖承诺锁拦截】方法族 '{old_family_id}' 当前仅投入 {steps_invested}/60 步，"
                            f"且尚未提交经沙箱反例脚本证实的死路证明 (barrier_proof.json)！"
                            f"严禁浅尝辄止打一枪换一个地方，请先使用 soft_flush 原地排查或提交可执行的反例证明脚本。"
                        ),
                    }

            fork_commit = ancestor_commit or state.get("anchor_s0_commit") or "GENESIS_S0"
            new_lineage_id = f"LIN-{new_family_id}-FORK-{int(time.time()) % 10000:04d}"

            brief_md = self.archive.build_scoped_l1_brief(
                node_id=slot_info["node_id"],
                slot_id=slot_id,
                family_id=new_family_id,
                lineage_id=new_lineage_id,
                parent_commit=fork_commit,
                targeted_code_block=new_targeted_block,
                hypothesis=new_hypothesis,
                step_budget=int(slot_info.get("step_budget", 25)),
                soft_flush_warning=f"已从祖先快照 {fork_commit} 硬分叉开启新血统 ({abandon_reason})",
            )

            island_dir = self.sandbox.checkout_clean_island(
                commit_hash=fork_commit,
                slot_dir_name=slot_id,
                scoped_brief_md=brief_md,
            )

            slot_info.update({
                "family_id": new_family_id,
                "lineage_id": new_lineage_id,
                "base_commit": fork_commit,
                "targeted_code_block": new_targeted_block,
                "hypothesis": new_hypothesis,
            })
            slot_info.pop("latest_commit", None)

            state.setdefault("lineages", {})[new_lineage_id] = {
                "family_id": new_family_id,
                "lineage_id": new_lineage_id,
                "forked_from_commit": fork_commit,
                "forked_from_lineage": old_lineage_id,
                "steps_invested": 0,
                "last_reflected_step": 0,
                "head_commit": fork_commit,
                "best_score": float(state.get("anchor_s0_score", 0.0)),
                "status": "ACTIVE_DEEPENING",
            }
            self.save_state(state)
            self._append_wal("ANCESTOR_HARD_FORK", {"slot_id": slot_id, "new_lineage_id": new_lineage_id, "fork_commit": fork_commit})

            return {
                "status": "OK",
                "action": "ANCESTOR_HARD_FORK",
                "slot_id": slot_id,
                "new_lineage_id": new_lineage_id,
                "forked_from_commit": fork_commit,
                "island_path": str(island_dir),
            }

    def submit_reflection_record(
        self,
        lineage_id: str,
        turn1_evidence_audit: str,
        turn2_attractor_diagnosis: str,
        turn3_pivot_decision: str,
        next_20_steps_contract: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        持久化 60 步原位 3 轮内省室审计契约 (`ReflectionRecord`, §7.6.3 & §8.1 #12)：
        写入 `.kernel_vault/reflections/REFLECT-<lineage_id>-<step>.json`，并更新谱系的 `last_reflected_step`。
        """
        with InterProcessFileLock(self.engine_lock_file):
            state = self.load_state()
            lineages = state.setdefault("lineages", {})
            if lineage_id not in lineages:
                return {"status": "ERROR", "message": f"找不到目标血统: {lineage_id}"}

            lin_state = lineages[lineage_id]
            step_now = int(lin_state.get("steps_invested", 60))
            reflection_id = f"REFLECT-{lineage_id}-{step_now}"

            record = {
                "reflection_id": reflection_id,
                "lineage_id": lineage_id,
                "family_id": lin_state.get("family_id", ""),
                "triggered_at_step": step_now,
                "three_turn_dialogue": {
                    "turn_1_evidence_vs_wishful_thinking": turn1_evidence_audit,
                    "turn_2_attractor_trap_diagnosis": turn2_attractor_diagnosis,
                    "turn_3_structural_pivot_decision": turn3_pivot_decision,
                },
                "next_20_steps_contract": next_20_steps_contract,
                "timestamp": time.time(),
            }
            out_file = self.reflections_dir / f"{reflection_id}.json"
            out_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

            lin_state["last_reflected_step"] = step_now
            lin_state["latest_reflection_id"] = reflection_id
            state["reflections_completed"] = int(state.get("reflections_completed", 0)) + 1
            self.save_state(state)
            self._append_wal("SUBMIT_REFLECTION", {"reflection_id": reflection_id, "lineage_id": lineage_id, "step": step_now})

            return {
                "status": "OK",
                "reflection_id": reflection_id,
                "reflection_file": str(out_file),
                "lineage_id": lineage_id,
                "last_reflected_step": step_now,
            }

    # ========================================================================
    # 5. 终局统稿、防吹牛核对与标准五件套交付信封编译 (Final Delivery Envelope)
    # ========================================================================

    def compile_final_delivery(self, executive_summary_md: str = "") -> Dict[str, Any]:
        """
        编译 `final_delivery/` 标准五件套终局交付目录，并执行三大防吹牛门禁检查 (§8.3.2)：
        1. 实验对比表格全部从带 HMAC 签名的 `leaderboard.json` 与 `claims.jsonl` 硬绑定渲染（严禁手敲捏造数字）；
        2. 扫描并拦截 `TODO` / `TBD` / `Conclusions Here` / `Insert Figure` 等模板占位符残留；
        3. 完整打包：
           - `01_executive_report.md`
           - `02_verified_source_code/` (最优 Commit 源码 + 全套已验证原语 `primitives/`)
           - `03_claim_evidence_ledger.json`
           - `04_reproduce_all.ps1`
           - `05_boundary_and_dead_ends_report.md`
        """
        forbidden_placeholders = [
            r"\bTODO\b", r"\bTBD\b", r"Conclusions Here", r"Insert Figure", r"\[PLACEHOLDER\]"
        ]
        found_placeholders = [
            pat for pat in forbidden_placeholders if re.search(pat, executive_summary_md, re.IGNORECASE)
        ]
        if found_placeholders:
            return {
                "status": "DELIVERY_BLOCKED_PLACEHOLDERS",
                "found_placeholders": found_placeholders,
                "message": "终局审计拦截：报告正文中存在未完成的模板占位符，请清理后重新生成！",
            }

        delivery_dir = self.workspace_root / "final_delivery"
        if delivery_dir.exists():
            force_cleanup_directory(delivery_dir, self.sandbox.graveyard_dir)
        delivery_dir.mkdir(parents=True, exist_ok=True)

        state = self.load_state()
        lb_data = json.loads(self.archive.leaderboard_file.read_text(encoding="utf-8"))
        entries = lb_data.get("entries", [])
        records = self.archive._read_jsonl(self.archive.records_file)
        claims = self.archive._read_jsonl(self.archive.claims_file)
        barriers = self.archive._read_jsonl(self.archive.barrier_proofs_file)

        table_lines = [
            "## 📊 独立沙箱实测性能演进总表（由内核从 HMAC 签名收据硬绑定生成）\n",
            "| 排名 | 节点编号 | 方法族 (Family) | 快照 Commit | Frozen 基准得分 | Live 挑战得分 | 运行耗时 (s) | 核心改进摘要 |",
            "| :---: | :--- | :--- | :--- | :---: | :---: | :---: | :--- |",
        ]
        for idx, item in enumerate(entries[:10], 1):
            table_lines.append(
                f"| {idx} | `{item['node_id']}` | `{item['family_id']}` | `{item['commit_hash'][:8]}` | "
                f"**{item['frozen_score']:.6f}** | {item['live_score']:.6f} | {item['wall_time_sec']:.2f} | {item['summary']} |"
            )

        report_content = (
            f"# 长城 Agent V4.2 终局技术报告 (`{state.get('task_id', 'CAMPAIGN')}`)\n\n"
            f"{executive_summary_md.strip()}\n\n---\n\n"
            + "\n".join(table_lines)
            + "\n"
        )
        (delivery_dir / "01_executive_report.md").write_text(report_content, encoding="utf-8")

        code_out_dir = delivery_dir / "02_verified_source_code"
        code_out_dir.mkdir(parents=True, exist_ok=True)
        best_commit = entries[0]["commit_hash"] if entries else state.get("anchor_s0_commit", "")
        best_snap_files = self.sandbox.snapshots_dir / best_commit / "files"
        if best_snap_files.exists():
            shutil.copytree(best_snap_files, code_out_dir, dirs_exist_ok=True)
        if self.archive.primitives_dir.exists():
            shutil.copytree(self.archive.primitives_dir, code_out_dir / "primitives", dirs_exist_ok=True)

        prim_manifest = json.loads(self.archive.primitives_manifest_file.read_text(encoding="utf-8")) if self.archive.primitives_manifest_file.exists() else {}
        ledger_bundle = {
            "task_id": state.get("task_id"),
            "anchor_s0_score": state.get("anchor_s0_score"),
            "best_champion": entries[0] if entries else None,
            "verified_claims": claims,
            "verified_barrier_proofs": barriers,
            "verified_primitives": [p.name for p in self.archive.primitives_dir.glob("*.py") if p.name != "__init__.py"],
            "primitives_manifest": prim_manifest.get("primitives", {}),
            "leaderboard_top10": entries[:10],
        }
        (delivery_dir / "03_claim_evidence_ledger.json").write_text(
            json.dumps(ledger_bundle, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        repro_ps1 = (
            "#!/usr/bin/env pwsh\n"
            "# Great Wall Agent V4.2 One-Click Clean-Room Reproduction Script\n"
            "$ErrorActionPreference = 'Stop'\n"
            "$env:PYTHONUTF8 = '1'\n"
            "$env:PYTHONHASHSEED = '42'\n"
            "$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path\n"
            "$env:PYTHONPATH = \"$ScriptDir/02_verified_source_code;$ScriptDir/../shared_readonly\"\n"
            "Write-Host '🚀 正在清洁室环境中复现最优冠军解...' -ForegroundColor Cyan\n"
            "python \"$ScriptDir/02_verified_source_code/src/main.py\"\n"
            "Write-Host '✅ 复现执行完成！' -ForegroundColor Green\n"
        )
        (delivery_dir / "04_reproduce_all.ps1").write_text(repro_ps1, encoding="utf-8")

        dead_lines = [
            "# 🚧 算法适用边界与死胡同避坑档案 (Boundary & Dead-Ends Report)\n",
            "## 一、经沙箱反例脚本证实的死路证明 (`barrier_proofs`)\n",
        ]
        if not barriers:
            dead_lines.append("*(无死路反例证明)*\n")
        else:
            for bp in barriers:
                dead_lines.append(
                    f"- **`[{bp.get('proof_id')}]`** (封禁方法族 `{bp.get('blocked_family_id')}`) — "
                    f"{bp.get('impossibility_statement')} (反例脚本: `{bp.get('counterexample_script')}`)"
                )
        dead_lines.append("\n## 二、已证伪的死胡同与负面实验记录 (`record_blacklist`)\n")
        if not records:
            dead_lines.append("*(无死胡同记录)*")
        else:
            for r in records:
                dead_lines.append(
                    f"- **`[{r.get('record_id')}]`** (节点 `{r.get('node_id')}`, 方法族 `{r.get('family_id')}`) — "
                    f"尝试机制: `{r.get('tried_mechanism')}` -> **失败原因**: {r.get('failure_summary')}"
                )
        (delivery_dir / "05_boundary_and_dead_ends_report.md").write_text("\n".join(dead_lines) + "\n", encoding="utf-8")

        self._append_wal("COMPILE_FINAL_DELIVERY", {"delivery_dir": str(delivery_dir), "best_commit": best_commit})
        return {
            "status": "OK",
            "delivery_dir": str(delivery_dir),
            "files_generated": [
                "01_executive_report.md",
                "02_verified_source_code/",
                "03_claim_evidence_ledger.json",
                "04_reproduce_all.ps1",
                "05_boundary_and_dead_ends_report.md",
            ],
            "best_champion": entries[0] if entries else None,
        }
