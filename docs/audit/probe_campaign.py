"""Full Great Wall campaign smoke test driven purely through MCP JSON-RPC over stdio.

Trail: gw_init_campaign -> gw_lock_distillation -> gw_allocate_slot -> gw_surgical_replace
       -> gw_evaluate_slot -> gw_submit_legacy -> gw_archive_query -> gw_compile_delivery
plus the second-slot lineage controls (soft_flush / hard_fork / differential_test /
deprecate_errata / submit_reflection) so all 9 tools get exercised.

Run:  python -B plugins/dsh-greatwall-agent/docs/audit/probe_campaign.py
Everything is created under %TEMP% (outside the repo).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp_client import MCPProc, is_error_result, tool_result_payload  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

AUDIT_DIR = Path(__file__).resolve().parent
STEPS: List[Dict[str, Any]] = []
LOG_LINES: List[str] = []


def log(msg: str) -> None:
    LOG_LINES.append(msg)
    print(msg)


def record(name: str, req: Dict[str, Any], resp: Dict[str, Any], expect: str, elapsed: float) -> Dict[str, Any]:
    payload = tool_result_payload(resp)
    is_err = is_error_result(resp)
    entry: Dict[str, Any] = {
        "step": name,
        "elapsed_sec": round(elapsed, 3),
        "request": req,
        "jsonrpc_response": resp.get("json"),
        "tool_payload": payload,
        "isError": is_err,
        "expect": expect,
    }
    STEPS.append(entry)
    log(
        f"\n### STEP {len(STEPS)}: {name}  ({elapsed:.2f}s)\n"
        f"REQ  = {json.dumps(req, ensure_ascii=False)}\n"
        f"RESP = {json.dumps(resp.get('json'), ensure_ascii=False)[:2500]}\n"
        f"PAYLOAD.status = {payload.get('status')!r}  isError={is_err}"
    )
    return payload


def main() -> int:
    tmp_root = Path(tempfile.mkdtemp(prefix="gw_audit_campaign_"))
    ws = tmp_root / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    ds = ws / "shared_readonly" / "datasets_public"
    ds.mkdir(parents=True, exist_ok=True)
    (ds / "train.csv").write_text(
        "id,feat_a,feat_b,target\n1,10.5,,1\n2,20.0,3.1,0\n3,,4.2,1\n", encoding="utf-8"
    )
    (ds / "meta.json").write_text(json.dumps([{"mol_id": "M1", "atoms": 12}, {"mol_id": "M2", "atoms": 18}]), encoding="utf-8")

    log(f"workspace = {ws}")
    p = MCPProc()
    init = p.initialize()
    log(f"initialize -> {json.dumps(init.get('json'), ensure_ascii=False)}")

    def call(name: str, args: Dict[str, Any], timeout: float = 180.0) -> Dict[str, Any]:
        req = {"name": name, "arguments": args}
        t0 = time.perf_counter()
        resp = p.call_tool(name, args, req_id=len(STEPS) + 10, timeout=timeout)
        el = time.perf_counter() - t0
        return {"req": req, "resp": resp, "elapsed": el}

    # ---------- 1. init ----------
    r = call("gw_init_campaign", {
        "workspaceRoot": str(ws),
        "taskId": "AUDIT_CAMPAIGN_中文_2026",
        "taskDescription": "审计用端到端全链路演练：多模态分子性质预测（临时工作区）",
        "domainType": "BIO_CHEM",
        "primaryMetric": "score",
        "higherIsBetter": True,
        "maxConcurrentSlots": 2,
        "totalStepBudget": 120,
        "resolvedAmbiguities": [{"question": "主指标?", "resolution": "score", "resolved_by": "audit"}],
    })
    init_payload = record("gw_init_campaign", r["req"], r["resp"], "status == OK", r["elapsed"])
    eda = init_payload.get("eda_probe_report", {})
    log(f"EDA total_files={eda.get('total_files')} modalities={[m.get('file') for m in eda.get('modalities', [])]}")

    # ---------- 2. lock distillation ----------
    cand_weak = "def solve(inputs):\n    return float(sum(inputs))\n"
    cand_strong = "def solve(inputs):\n    return float(sum(v * v for v in inputs))\n"
    r = call("gw_lock_distillation", {
        "workspaceRoot": str(ws),
        "orthogonalFamilies": [
            {"family_id": "FAM-01", "family_name": "Equivariant GNN", "custom_zone": "message passing"},
            {"family_id": "FAM-02", "family_name": "Modern GBDT", "custom_zone": "descriptors"},
        ],
        "candidateBaselines": [
            {"name": "CAND_WEAK", "code": cand_weak},
            {"name": "CAND_STRONG", "code": cand_strong},
        ],
        "obsoleteBlacklist": ["LogisticRegression / Ridge as final model"],
        "mustReuseLibraries": ["sklearn.model_selection.StratifiedKFold"],
        "pitfallGuardrails": ["CV 折内独立 fit"],
    })
    lock_payload = record("gw_lock_distillation", r["req"], r["resp"], "status == OK and anchor_s0_score > 0", r["elapsed"])
    log(f"s0_commit={lock_payload.get('anchor_s0_commit')} s0_score={lock_payload.get('anchor_s0_score')} "
        f"tournament={lock_payload.get('candidate_tournament_log')}")

    # ---------- 3. allocate ----------
    r = call("gw_allocate_slot", {
        "workspaceRoot": str(ws),
        "familyId": "FAM-01",
        "targetedCodeBlock": "solve",
        "hypothesis": "平方和输入特征后再线性放大能提升 score",
        "stepBudget": 25,
    })
    alloc_payload = record("gw_allocate_slot", r["req"], r["resp"], "status == OK", r["elapsed"])
    slot_id = alloc_payload.get("slot_id", "")
    island = Path(alloc_payload.get("island_path", str(ws / "worktrees" / slot_id)))
    log(f"slot_id={slot_id} island={island} brief_exists={(island / 'scoped_brief.md').exists()}")

    # ---------- 4. surgical replace ----------
    new_block = "def solve(inputs):\n    return float(sum(v * v for v in inputs)) * 2.0\n"
    r = call("gw_surgical_replace", {
        "workspaceRoot": str(ws),
        "slotId": slot_id,
        "targetBlockName": "solve",
        "newBlockCode": new_block,
    })
    sr_payload = record("gw_surgical_replace", r["req"], r["resp"], "status == OK", r["elapsed"])
    main_py = island / "src" / "main.py"
    log(f"main.py after replace:\n{main_py.read_text(encoding='utf-8') if main_py.exists() else '<missing>'}")
    diff_patch = island / "legacy_out" / "diff.patch"
    log(f"diff.patch exists={diff_patch.exists()} size={diff_patch.stat().st_size if diff_patch.exists() else 0}")

    # ---------- 5a. AST gate negative probe: claim a variable that does not exist ----------
    r = call("gw_evaluate_slot", {
        "workspaceRoot": str(ws),
        "slotId": slot_id,
        "entryScript": "src/main.py",
        "claimedSweptVariables": ["scale"],
        "timeoutSec": 60,
    })
    gate = record("gw_evaluate_slot/AST-gate-reject", r["req"], r["resp"], "status == REJECTED_BY_AST_AUDITOR", r["elapsed"])
    log(f"AST gate (expected rejection) status={gate.get('status')} claim_mismatch={gate.get('claim_code_mismatch')}")

    # ---------- 5b. clean evaluate ----------
    r = call("gw_evaluate_slot", {
        "workspaceRoot": str(ws),
        "slotId": slot_id,
        "entryScript": "src/main.py",
        "operatorDescription": "平方和算子放大",
        "timeoutSec": 60,
    })
    eval_payload = record("gw_evaluate_slot", r["req"], r["resp"], "scores present / no crash", r["elapsed"])
    log(f"triage={eval_payload.get('triage_tier')} scores={eval_payload.get('scores')} "
        f"status={eval_payload.get('status')} error={eval_payload.get('message')}")
    receipt_path = island / "legacy_out" / "metrics_receipt.json"
    log(f"receipt exists={receipt_path.exists()}")

    # ---------- 6. build the 5-item legacy bundle, then submit ----------
    legacy = island / "legacy_out"
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / "epitaph.md").write_text("已在门控探针中验证平方和特征放大带来的真实提分，未发现数据泄漏。\n", encoding="utf-8")
    prim_dir = legacy / "primitives"
    prim_dir.mkdir(exist_ok=True)
    (prim_dir / "sum_squares.py").write_text(
        '"""已验证平方和原语。"""\n'
        "def sum_squares(xs):\n"
        '    """返回平方和。"""\n'
        "    return float(sum(x * x for x in xs))\n"
        "\n"
        "def test_sum_squares():\n"
        "    assert sum_squares([1, 2]) == 5.0\n"
        "    assert sum_squares([]) == 0.0\n",
        encoding="utf-8",
    )
    (legacy / "last_will_proposals.json").write_text(json.dumps([
        {"action_type": "EXTEND", "falsifiable_hypothesis": "将平方和扩展到三阶矩可再提升 2%", "priority_score": 0.8}
    ], ensure_ascii=False, indent=2), encoding="utf-8")
    (legacy / "claims.json").write_text(json.dumps([
        {"statement": "平方和特征放大对 score 的提升在 60s 沙箱内可复现", "depends_on": []}
    ], ensure_ascii=False, indent=2), encoding="utf-8")

    r = call("gw_submit_legacy", {"workspaceRoot": str(ws), "slotId": slot_id, "stepsConsumed": 20})
    sub_payload = record("gw_submit_legacy", r["req"], r["resp"], "status == OK", r["elapsed"])
    record_id = sub_payload.get("admitted_record_id", "")
    log(f"submit status={sub_payload.get('status')} errors={sub_payload.get('errors')} "
        f"rank={sub_payload.get('leaderboard_rank')} prims={sub_payload.get('admitted_primitives')} "
        f"record={record_id}")

    # ---------- 7. archive query ----------
    r = call("gw_archive_query", {"workspaceRoot": str(ws), "action": "get_l0_index"})
    l0 = record("gw_archive_query/get_l0_index", r["req"], r["resp"], "status == OK", r["elapsed"])
    log(f"L0 chars={len(l0.get('l0_index_markdown', ''))}")

    r = call("gw_archive_query", {"workspaceRoot": str(ws), "action": "get_l2_item", "itemId": "sum_squares"})
    l2 = record("gw_archive_query/get_l2_item(primitive)", r["req"], r["resp"], "type == primitive", r["elapsed"])
    log(f"L2 type={l2.get('type')}")

    if record_id:
        r = call("gw_archive_query", {"workspaceRoot": str(ws), "action": "get_l2_item", "itemId": record_id})
        rec = record("gw_archive_query/get_l2_item(record)", r["req"], r["resp"], "type == record_blacklist", r["elapsed"])
        log(f"record L2 type={rec.get('type')}")

    r = call("gw_archive_query", {"workspaceRoot": str(ws), "action": "get_campaign_status"})
    st = record("gw_archive_query/get_campaign_status", r["req"], r["resp"], "status == OK", r["elapsed"])
    log(f"campaign stage={st.get('campaign_stage')} steps={st.get('campaign_state', {}).get('total_steps_executed')}")

    # ---------- 8. compile delivery (placeholder negative test first) ----------
    r = call("gw_compile_delivery", {"workspaceRoot": str(ws), "executiveSummaryMd": "TODO: 这里还没写"})
    blk = record("gw_compile_delivery/placeholder-blocked", r["req"], r["resp"], "status == DELIVERY_BLOCKED_PLACEHOLDERS", r["elapsed"])
    log(f"placeholder gate status={blk.get('status')} isError={STEPS[-1]['isError']}")

    r = call("gw_compile_delivery", {
        "workspaceRoot": str(ws),
        "executiveSummaryMd": "## 方法论\n使用平方和特征放大算子，经 HMAC 收据核验提分。\n\n## 消融\n对比零号基线 s_0 的提升见表。",
    })
    dlv = record("gw_compile_delivery", r["req"], r["resp"], "status == OK", r["elapsed"])
    files = dlv.get("files_generated", [])
    log(f"delivery status={dlv.get('status')} files={files} dir_exists={(ws / 'final_delivery').exists()}")
    for rel in files:
        fp = ws / "final_delivery" / rel.rstrip("/")
        log(f"  - {rel}: exists={fp.exists()}")

    # ---------- 9. second slot: lineage controls ----------
    r = call("gw_allocate_slot", {
        "workspaceRoot": str(ws),
        "familyId": "FAM-02",
        "targetedCodeBlock": "solve",
        "hypothesis": "GBDT 描述子交叉",
        "stepBudget": 25,
    })
    alloc2 = record("gw_allocate_slot#2", r["req"], r["resp"], "status == OK", r["elapsed"])
    slot2 = alloc2.get("slot_id", "")
    island2 = Path(alloc2.get("island_path", ""))
    log(f"slot2={slot2} island2={island2}")

    r = call("gw_lineage_control", {
        "workspaceRoot": str(ws),
        "action": "soft_flush",
        "slotId": slot2,
        "failureEpitaph": "改乱了解析逻辑导致 NameError",
        "newTargetedBlock": "solve",
        "newHypothesis": "回到干净快照重试",
    })
    sf = record("gw_lineage_control/soft_flush", r["req"], r["resp"], "status == OK", r["elapsed"])
    log(f"soft_flush status={sf.get('status')} restored={sf.get('restored_commit')}")

    # hard fork with an invalid ancestor commit (records silent-empty-island behaviour)
    r = call("gw_lineage_control", {
        "workspaceRoot": str(ws),
        "action": "hard_fork",
        "slotId": slot2,
        "ancestorCommit": "NO_SUCH_COMMIT_0000",
        "newFamilyId": "FAM-02",
        "newTargetedBlock": "solve",
        "newHypothesis": "非法祖先提交测试",
    })
    hf_bad = record("gw_lineage_control/hard_fork(bad ancestor)", r["req"], r["resp"], "should reject unknown commit", r["elapsed"])
    log(f"hard_fork(bad) status={hf_bad.get('status')} island_src_files="
        f"{[x.name for x in (island2 / 'src').glob('*')] if (island2 / 'src').exists() else 'src-missing'}")

    r = call("gw_lineage_control", {
        "workspaceRoot": str(ws),
        "action": "hard_fork",
        "slotId": slot2,
        "ancestorCommit": lock_payload.get("anchor_s0_commit") or "",
        "newFamilyId": "FAM-02",
        "newTargetedBlock": "solve",
        "newHypothesis": "从 s0 硬分叉",
    })
    hf = record("gw_lineage_control/hard_fork", r["req"], r["resp"], "status == OK", r["elapsed"])
    log(f"hard_fork status={hf.get('status')} new_lineage={hf.get('new_lineage_id')}")

    # differential test between s0 anchor code and the improved main.py (from snapshot)
    script_a = ws / "shared_readonly" / "distilled" / "anchor_baseline.py"
    script_b = ws / "final_delivery" / "02_verified_source_code" / "src" / "main.py"
    r = call("gw_lineage_control", {
        "workspaceRoot": str(ws),
        "action": "differential_test",
        "scriptAPath": str(script_a),
        "scriptBPath": str(script_b),
        "stressInputs": [[1, 2], [0], [-5, 5]],
    })
    dt = record("gw_lineage_control/differential_test", r["req"], r["resp"], "status == OK", r["elapsed"])
    log(f"differential consistent={dt.get('consistent')} divergent={len(dt.get('divergent_cases', []))}")

    # deprecate errata (no history case scores -> expect OK with recomputed_count 0)
    r = call("gw_lineage_control", {
        "workspaceRoot": str(ws),
        "action": "deprecate_errata",
        "errataCaseId": "CASE-001",
        "errataReason": "生成器 NaN bug",
    })
    de = record("gw_lineage_control/deprecate_errata", r["req"], r["resp"], "status == OK", r["elapsed"])
    log(f"deprecate status={de.get('status')} recomputed={de.get('recomputed_count')}")

    # submit_reflection on an existing lineage
    r = call("gw_lineage_control", {
        "workspaceRoot": str(ws),
        "action": "submit_reflection",
        "lineageId": hf.get("new_lineage_id") or "LIN-FAM-02",
        "turn1EvidenceAudit": "证据: 收据分数可复现",
        "turn2AttractorDiagnosis": "陷阱: 未出现定性画图逃避",
        "turn3PivotDecision": "转向: 扩展三阶矩",
        "next20StepsContract": {"max_structural_change": 0.3},
    })
    rf = record("gw_lineage_control/submit_reflection", r["req"], r["resp"], "status == OK", r["elapsed"])
    log(f"reflection status={rf.get('status')} id={rf.get('reflection_id')}")

    # clean up slot2 by soft-flushing then submitting nothing is not allowed; just leave it in place
    rc, err_tail = p.close()
    log(f"\nserver exit code on EOF = {rc}; stderr_tail={[x.decode('utf-8','replace')[-200:] for x in err_tail][-3:]}")

    summary = {
        "workspace": str(ws),
        "server": str(Path(p.server)),
        "python": sys.version,
        "steps_total": len(STEPS),
        "steps_with_isError_true": [s["step"] for s in STEPS if s["isError"]],
        "steps": STEPS,
        "server_exit_code": rc,
        "server_stderr_tail": [x.decode("utf-8", "replace") for x in err_tail],
    }
    (AUDIT_DIR / "campaign_result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (AUDIT_DIR / "campaign_run.log").write_text("\n".join(LOG_LINES) + "\n", encoding="utf-8")
    print("\n=== campaign trail ===")
    for i, s in enumerate(STEPS, 1):
        print(f"{i:02d}. {s['step']:<48} isError={s['isError']} status={s['tool_payload'].get('status')} ({s['elapsed_sec']}s)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        (AUDIT_DIR / "campaign_run.log").write_text("\n".join(LOG_LINES) + "\n" + traceback.format_exc(), encoding="utf-8")
        sys.exit(1)
