"""Probe: submit_legacy_and_release_slot validates/admits the legacy bundle into the archive
BEFORE verifying the HMAC receipt signature (engine.py:628-653 ordering).

Run:  python -B plugins/dsh-greatwall-agent/docs/audit/probe_submit_order.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

AUDIT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = AUDIT_DIR.parents[2] / "greatwall-agent"
sys.path.insert(0, str(PLUGIN_ROOT))

from lib.engine import GreatWallEngine  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="gw_audit_order_"))
    ws = tmp / "ws"
    (ws / "shared_readonly" / "datasets_public").mkdir(parents=True, exist_ok=True)
    result: Dict[str, Any] = {"workspace": str(ws)}
    try:
        engine = GreatWallEngine(ws)
        engine.init_campaign(task_id="ORDER", task_description="ordering probe")
        engine.lock_opening_distillation(
            orthogonal_families=[{"family_id": "FAM-01", "family_name": "Fam"}],
            candidate_baselines=[{"name": "C", "code": "def solve(inputs):\n    return float(sum(inputs))\n"}],
        )
        alloc = engine.allocate_exploration_slot("FAM-01", "solve", "h", step_budget=10)
        slot = alloc["slot_id"]
        island = Path(alloc["island_path"])
        receipt = engine.evaluate_slot(slot, timeout_sec=30)
        result["receipt_before"] = {"status": receipt.get("status"), "frozen": import_frozen(receipt)}

        legacy = island / "legacy_out"
        legacy.mkdir(parents=True, exist_ok=True)
        (legacy / "epitaph.md").write_text("门控探针：为验证伪造收据时的副作用顺序。\n", encoding="utf-8")
        (legacy / "last_will_proposals.json").write_text(json.dumps([
            {"action_type": "REPAIR", "falsifiable_hypothesis": "修复后应可复现"}
        ], ensure_ascii=False), encoding="utf-8")
        prim = legacy / "primitives"
        prim.mkdir(exist_ok=True)
        (prim / "audit_side_effect.py").write_text(
            '"""副作用顺序探针原语。"""\n'
            "def helper(x):\n"
            '    """d"""\n'
            "    return x\n"
            "def test_helper():\n"
            "    assert helper(1) == 1\n",
            encoding="utf-8",
        )

        # tamper the receipt without re-signing: score is now forged
        receipt_path = legacy / "metrics_receipt.json"
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
        data["scores"]["frozen_benchmark"] = float(data["scores"]["frozen_benchmark"]) + 1000.0
        receipt_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        res = engine.submit_legacy_and_release_slot(slot, steps_consumed=10)
        result["submit_status"] = res.get("status")
        result["submit_message"] = res.get("message")
        result["submit_errors"] = res.get("errors")

        archive_prim = ws / "shared_readonly" / "archive" / "ledger" / "primitives" / "audit_side_effect.py"
        manifest = ws / "shared_readonly" / "archive" / "ledger" / "primitives_manifest.json"
        claims = ws / "shared_readonly" / "archive" / "ledger" / "claims.jsonl"
        records = ws / "shared_readonly" / "archive" / "record_blacklist.jsonl"
        manifest_data = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
        result["side_effects_after_forged_receipt"] = {
            "primitive_copied_into_archive": archive_prim.exists(),
            "primitive_registered_in_manifest": "audit_side_effect" in (manifest_data.get("primitives") or {}),
            "record_blacklist_written": records.exists() and records.read_text(encoding="utf-8").count("\n") > 0,
            "island_still_present": island.exists(),
            "state_slot_still_active": slot in (engine.load_state().get("active_slots") or {}),
        }
        confirmed = (
            result["submit_status"] == "FORGED_RECEIPT_DETECTED"
            and result["side_effects_after_forged_receipt"]["primitive_copied_into_archive"]
            and result["side_effects_after_forged_receipt"]["primitive_registered_in_manifest"]
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"\n[{'CONFIRMED' if confirmed else 'not-reproduced'}] H1 forged receipt rejected AFTER archive admission")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    (AUDIT_DIR / "submit_order_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def import_frozen(receipt: Dict[str, Any]) -> Any:
    try:
        return receipt["scores"]["frozen_benchmark"]
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
