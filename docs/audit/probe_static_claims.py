"""Small static-claim probes for lib/evaluator.py behaviours that are easy to get wrong.

Run:  python -B plugins/dsh-greatwall-agent/docs/audit/probe_static_claims.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

AUDIT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = AUDIT_DIR.parents[2] / "greatwall-agent"
sys.path.insert(0, str(PLUGIN_ROOT))

from lib.evaluator import ASTCodeInspector, IsolatedEvaluator  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

RESULTS: List[Dict[str, Any]] = []


def record(cid: str, title: str, ok: bool, evidence: Any) -> None:
    RESULTS.append({"id": cid, "title": title, "confirmed": bool(ok), "evidence": evidence})
    print(f"[{'CONFIRMED' if ok else 'not-reproduced'}] {cid} {title}\n    {json.dumps(evidence, ensure_ascii=False, default=str)[:1200]}\n")


def main() -> int:
    # 1. blacklist matching is a raw regex over the whole source text: a comment/string triggers rejection
    code_comment = (
        "def solve(x):\n"
        "    # 我们评估后放弃了 LogisticRegression 作为最终模型，仅保留注释供审查\n"
        "    return float(x)\n"
    )
    rep = ASTCodeInspector.inspect_code(
        code_comment,
        obsolete_blacklist=["LogisticRegression / Ridge as final model"],
    )
    record(
        "K1",
        "过时模型黑名单用裸正则扫描全文：注释/字符串里提到被禁方案也会导致整份代码被拒（误杀）",
        rep.passed is False,
        {"passed": rep.passed, "contract_violations": rep.contract_violations, "source": code_comment},
    )

    # 2. claimed swept variable: two constant assignments outside any loop are treated as "dynamic"
    code_static = (
        "def solve(x):\n"
        "    e = 2\n"
        "    if x > 100:\n"
        "        e = 3\n"
        "    return float(x) * e\n"
    )
    rep2 = ASTCodeInspector.inspect_code(code_static, claimed_swept_variables=["e"])
    record(
        "K2",
        "声明-代码对账可被绕过：同一常量变量在死分支里再赋一次常数，即被判定为“动态探索”",
        rep2.passed is True and not rep2.claim_code_mismatch,
        {
            "passed": rep2.passed,
            "claim_code_mismatch": rep2.claim_code_mismatch,
            "source": code_static,
            "note": "_verify_variable_is_dynamic: constant_assignments>1 => True (evaluator.py:331-332)",
        },
    )

    # 3. subprocess / os are NOT forbidden imports/calls although ctypes/socket are
    code_shell = (
        "import subprocess, os\n"
        "def solve(x):\n"
        "    subprocess.run(['cmd', '/c', 'whoami'])\n"
        "    os.system('dir')\n"
        "    return float(x)\n"
    )
    rep3 = ASTCodeInspector.inspect_code(code_shell)
    record(
        "K3",
        "AST 反作弊只禁 ctypes/socket/eval 等，允许 subprocess/os.system 直接执行任意系统命令",
        rep3.passed is True,
        {"passed": rep3.passed, "violations": rep3.security_violations, "source": code_shell},
    )

    # 4. metrics parser: a bare JSON line on stdout is accepted as the metrics dict
    parsed_bare = IsolatedEvaluator._extract_metrics_from_stdout(
        "some candididate log\n{\"frozen_score\": 5.0, \"live_score\": 5.0}\n"
    )
    parsed_marker = IsolatedEvaluator._extract_metrics_from_stdout(
        "__GW_METRICS_JSON__:{\"frozen_score\": 1.0}\n__GW_METRICS_JSON__:{\"frozen_score\": 2.0}\n"
    )
    record(
        "K4",
        "_extract_metrics_from_stdout 兜底接受任意裸 JSON 行；标记行取“最后一个”（可被 atexit 覆盖）",
        parsed_bare.get("frozen_score") == 5.0 and parsed_marker.get("frozen_score") == 2.0,
        {"bare_json_parsed": parsed_bare, "duplicate_marker_last_wins": parsed_marker},
    )

    # 5. structural diff ratio ignores values and names but also ignores branch/operator semantics
    same_structure = (
        "def solve(x):\n    return x * 2\n"
    )
    changed_operator = (
        "def solve(x):\n    return x * 2\n"
    )
    ratio = ASTCodeInspector.compute_structural_diff_ratio(
        "def solve(x):\n    if x > 0:\n        return x * 2\n    return 0\n",
        "def solve(x):\n    if x > 0:\n        return x * 2\n    return 0\n",
    )
    record(
        "K5",
        "结构改动率对完全相同的代码为 0（正常）；常量/变量名改动不计入（设计如此，记录为限制）",
        ratio == 0.0,
        {"ratio_identical": ratio, "note": "structural_diff_ratio 只统计 AST 节点类型计数，变量/常量/运算符全部同权"},
    )

    out = {"results": RESULTS, "confirmed": [r["id"] for r in RESULTS if r["confirmed"]]}
    (AUDIT_DIR / "static_claims_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"=== {len(out['confirmed'])}/{len(RESULTS)} confirmed -> static_claims_result.json ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
