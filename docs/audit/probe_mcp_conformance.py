"""MCP / JSON-RPC stdio conformance probe for bin/gw_mcp_server.py.

Run:  python -B plugins/dsh-greatwall-agent/docs/audit/probe_mcp_conformance.py

Every check prints PASS/FAIL plus an evidence snippet. Raw transcript is written to
mcp_conformance_result.json next to this file.
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
from mcp_client import MCPProc, SERVER, is_error_result, tool_result_payload  # noqa: E402

AUDIT_DIR = Path(__file__).resolve().parent
RESULTS: List[Dict[str, Any]] = []

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

EXPECTED_TOOLS = [
    "gw_init_campaign",
    "gw_lock_distillation",
    "gw_allocate_slot",
    "gw_surgical_replace",
    "gw_evaluate_slot",
    "gw_submit_legacy",
    "gw_lineage_control",
    "gw_archive_query",
    "gw_compile_delivery",
]


def check(name: str, ok: bool, evidence: Any) -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "evidence": evidence})
    tag = "PASS" if ok else "FAIL"
    text = json.dumps(evidence, ensure_ascii=False, default=str) if not isinstance(evidence, str) else evidence
    print(f"[{tag}] {name}\n        evidence: {text[:1200]}")


def crash_probe(label: str, frame: bytes, timeout: float = 6.0) -> Dict[str, Any]:
    """Send a raw frame to a fresh server and observe survival vs crash."""
    p = MCPProc()
    out: Dict[str, Any] = {"label": label, "frame": frame.decode("utf-8", "replace")}
    try:
        p.initialize()
        try:
            p.send_raw(frame)
        except OSError as e:  # server already died
            out["write_error"] = f"{type(e).__name__}: {e}"
        line = p.read_line(timeout=timeout)
        out["response_raw"] = None if line is None else line.decode("utf-8", "replace")
        time.sleep(0.15)
        if p.proc.poll() is None:
            try:
                r = p.rpc(99, "tools/list", timeout=6.0)
                out["alive_after_frame"] = "json" in r and r["json"].get("jsonrpc") == "2.0"
                if out["alive_after_frame"]:
                    out["post_frame_tools_count"] = len(r["json"]["result"]["tools"])
            except OSError as e:
                out["alive_after_frame"] = False
                out["post_write_error"] = f"{type(e).__name__}: {e}"
            except Exception as e:  # noqa: BLE001
                out["alive_after_frame"] = False
                out["post_frame_error"] = f"{type(e).__name__}: {e}"
        else:
            out["alive_after_frame"] = False
        out["exit_code"] = p.proc.poll()
        _, err_tail = p.close(timeout=5.0)
        out["stderr_tail"] = [x.decode("utf-8", "replace") for x in err_tail][-12:]
        out["stderr_traceback_saved"] = _save_crash_stderr(label, err_tail)
    except Exception:  # noqa: BLE001
        out["probe_exception"] = traceback.format_exc()
        p.kill()
    return out


_CRASH_SEQ = [0]


def _save_crash_stderr(label: str, err_tail: List[bytes]) -> str:
    _CRASH_SEQ[0] += 1
    safe = "".join(c if c.isalnum() else "_" for c in label)[:40]
    path = AUDIT_DIR / f"crash_stderr_{_CRASH_SEQ[0]:02d}_{safe}.txt"
    try:
        path.write_text(b"".join(err_tail).decode("utf-8", "replace"), encoding="utf-8")
        return str(path)
    except Exception:
        return ""


def main() -> int:
    tmp_ws = Path(tempfile.mkdtemp(prefix="gw_audit_ws_"))
    # a couple of dataset files so the EDA probe has content
    ds = tmp_ws / "shared_readonly" / "datasets_public"
    ds.mkdir(parents=True, exist_ok=True)
    (ds / "train.csv").write_text("id,feat,target\n1,0.5,1\n2,,0\n", encoding="utf-8")
    (ds / "meta.json").write_text(json.dumps([{"mol_id": "M1"}]), encoding="utf-8")

    print(f"server   = {SERVER}")
    print(f"python   = {sys.executable} {sys.version.split()[0]}")
    print(f"tmp_ws   = {tmp_ws}\n")

    p = MCPProc()
    t0 = time.perf_counter()
    init = p.rpc(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "probe", "version": "1"}})
    init_ms = round((time.perf_counter() - t0) * 1000, 1)
    check(
        "initialize returns MCP result",
        "json" in init and init["json"].get("result", {}).get("protocolVersion") == "2024-11-05",
        {"latency_ms": init_ms, "response": init.get("json")},
    )

    # notification with no id must produce no reply
    p.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    line = p.read_line(timeout=1.0)
    check("notifications/initialized is silent", line in (b"<TIMEOUT>", None), {"line": None if line is None else line.decode("utf-8", "replace")})

    # unknown notification (no id) must also stay silent
    p.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}})
    line2 = p.read_line(timeout=1.0)
    check("unknown notification is silent (no -32601 spam)", line2 in (b"<TIMEOUT>", None), {"line": None if line2 is None else line2.decode("utf-8", "replace")})

    # tools/list
    tl = p.rpc(2, "tools/list")
    tools = tl.get("json", {}).get("result", {}).get("tools", [])
    names = [t.get("name") for t in tools]
    schema_ok = all(
        isinstance(t.get("inputSchema"), dict) and t["inputSchema"].get("type") == "object"
        and "workspaceRoot" in (t["inputSchema"].get("properties") or {})
        for t in tools
    )
    required_ok = all("workspaceRoot" in (t["inputSchema"].get("required") or []) for t in tools)
    check("tools/list exposes exactly 9 expected tools", names == EXPECTED_TOOLS, {"tools": names})
    check("every inputSchema is object with workspaceRoot", schema_ok and required_ok, {"schema_ok": schema_ok, "required_ok": required_ok})

    # happy path: gw_archive_query get_l0_index (creates workspace scaffolding only inside tmp_ws)
    call = p.call_tool("gw_archive_query", {"workspaceRoot": str(tmp_ws), "action": "get_l0_index"}, req_id=3)
    payload = tool_result_payload(call)
    check(
        "tools/call happy path (archive get_l0_index)",
        call.get("json", {}).get("result", {}).get("isError") is False and payload.get("status") == "OK",
        {"isError": is_error_result(call), "payload_keys": list(payload.keys()), "l0_first_line": str(payload.get("l0_index_markdown", ""))[:80]},
    )

    # UTF-8 round-trip through arguments (Chinese + emoji) and back
    call_utf = p.call_tool(
        "gw_init_campaign",
        {"workspaceRoot": str(tmp_ws), "taskId": "审计任务_中文😀", "taskDescription": "验证 UTF-8 往返与 Windows 编码"},
        req_id=4,
    )
    utf_payload = tool_result_payload(call_utf)
    utf_ok = (
        call_utf.get("json", {}).get("result", {}).get("isError") is False
        and utf_payload.get("status") == "OK"
    )
    ws_text_ok = True
    try:
        import csv  # noqa: F401
        cfg = (tmp_ws / "shared_readonly" / "task_config.yaml").read_text(encoding="utf-8")
        ws_text_ok = "审计任务_中文😀" in cfg
    except Exception as e:
        ws_text_ok = f"read failed: {e}"
    check("UTF-8 arguments round-trip (Chinese+emoji)", utf_ok and ws_text_ok is True, {"isError": is_error_result(call_utf), "task_config_contains": ws_text_ok})

    # malformed JSON must yield -32700 and keep the server alive
    p.send_raw(b'{oops not json\n')
    line = p.read_line(timeout=5.0)
    try:
        parse_err = json.loads(line.decode("utf-8")) if line and line != b"<TIMEOUT>" else {}
    except Exception:
        parse_err = {}
    alive = p.rpc(5, "tools/list", timeout=5.0)
    check(
        "malformed JSON -> -32700 and server survives",
        parse_err.get("error", {}).get("code") == -32700 and parse_err.get("id") is None,
        {"error_frame": parse_err, "alive": "_raw" in alive and alive["_raw"] not in (None, "<TIMEOUT>")},
    )

    # unknown method -> -32601 with id echoed
    um = p.rpc(6, "no/such/method")
    check(
        "unknown method -> -32601",
        um.get("json", {}).get("error", {}).get("code") == -32601 and um.get("json", {}).get("id") == 6,
        um.get("json"),
    )

    # string id echo
    sid = p.rpc("req-abc", "tools/list")
    check("string id echoed verbatim", sid.get("json", {}).get("id") == "req-abc", {"id": sid.get("json", {}).get("id")})

    # missing required args -> tool-level isError (must NOT be a crash)
    miss = p.call_tool("gw_surgical_replace", {"workspaceRoot": str(tmp_ws)}, req_id=7)
    miss_j = miss.get("json", {})
    miss_text = json.dumps(miss_j, ensure_ascii=False)
    check(
        "missing required args -> JSON-RPC result with isError=true",
        miss_j.get("result", {}).get("isError") is True and "KeyError" in miss_text,
        {"isError": is_error_result(miss), "snippet": miss_text[:400]},
    )

    # unknown tool
    unk = p.call_tool("gw_not_a_tool", {"workspaceRoot": str(tmp_ws)}, req_id=8)
    check(
        "unknown tool name -> isError=true",
        unk.get("json", {}).get("result", {}).get("isError") is True,
        {"text": unk.get("json", {}).get("result", {}).get("content", [{}])[0].get("text", "")[:200]},
    )

    # tool-level runtime error (not-initialized campaign collision, forced by bogus slot)
    terr = p.call_tool("gw_evaluate_slot", {"workspaceRoot": str(tmp_ws), "slotId": "slot_99_missing"}, req_id=9)
    check(
        "tool-level status=ERROR is reported as isError=true",
        terr.get("json", {}).get("result", {}).get("isError") is True,
        {"isError": is_error_result(terr), "text": terr.get("json", {}).get("result", {}).get("content", [{}])[0].get("text", "")[:200]},
    )

    # stdout purity: every line the server wrote must be a JSON-RPC frame
    bad_lines: List[str] = []
    frames = 0
    for raw in p.raw_out:
        try:
            obj = json.loads(raw.decode("utf-8"))
            if not isinstance(obj, dict) or obj.get("jsonrpc") != "2.0":
                bad_lines.append(raw.decode("utf-8", "replace"))
            else:
                frames += 1
        except Exception:
            bad_lines.append(raw.decode("utf-8", "replace"))
    check("stdout contains ONLY JSON-RPC frames", not bad_lines, {"frames": frames, "bad_lines": bad_lines[:5]})

    # stderr usage: the server should stay quiet on the normal path
    stderr_lines = [x.decode("utf-8", "replace").rstrip("\n") for x in p.drain_stderr(0.5)]
    check("stderr quiet during normal operation", stderr_lines == [], {"stderr": stderr_lines[:5]})

    # workspaceRoot is "required" but simply omitted -> silently falls back to the server process cwd
    fb = p.call_tool("gw_archive_query", {"action": "get_l0_index"}, req_id=10)
    fb_payload = tool_result_payload(fb)
    created = {
        "vault": (p.cwd / ".kernel_vault").exists(),
        "secret": (p.cwd / ".kernel_vault" / "hmac_secret.key").exists(),
        "shared_readonly": (p.cwd / "shared_readonly").exists(),
        "worktrees": (p.cwd / "worktrees").exists(),
    }
    check(
        "缺省 workspaceRoot 时回退到服务端 cwd，并在那里创建完整运行工作区",
        fb_payload.get("status") == "OK" and all(created.values()),
        {"server_cwd": str(p.cwd), "response_status": fb_payload.get("status"), "isError": is_error_result(fb), "created": created},
    )

    rc, err_tail = p.close()
    check("clean shutdown on stdin EOF (exit code 0)", rc == 0, {"exit_code": rc, "stderr_tail": [x.decode('utf-8', 'replace')[-300:] for x in err_tail][-3:]})

    # ---- crash probes: malformed-but-valid JSON frames ----
    for label, frame in [
        ("JSON array (JSON-RPC batch)", b'[{"jsonrpc":"2.0","id":1,"method":"tools/list"}]\n'),
        ("JSON null", b'null\n'),
        ("JSON number", b'123\n'),
        ("JSON string", b'"hello"\n'),
        ("params as array on tools/call", b'{"jsonrpc":"2.0","id":50,"method":"tools/call","params":[]}\n'),
        ("request without method", b'{"jsonrpc":"2.0","id":51}\n'),
    ]:
        res = crash_probe(label, frame)
        RESULTS.append({"name": f"survives frame: {label}", "ok": bool(res.get("alive_after_frame")), "evidence": res})
        tag = "PASS" if res.get("alive_after_frame") else "FAIL"
        print(f"[{tag}] survives frame: {label}\n        evidence: {json.dumps(res, ensure_ascii=False)[:1400]}")

    # content-length style frame (LSP framing) — not required by MCP 2024-11-05, recorded for the bridge
    res = crash_probe("LSP Content-Length framing", b'Content-Length: 55\r\n\r\n{"jsonrpc":"2.0","id":60,"method":"tools/list"}', timeout=3.0)
    RESULTS.append({"name": "LSP Content-Length framing behaviour", "ok": True, "evidence": res})
    print(f"[INFO] LSP Content-Length framing\n        evidence: {json.dumps(res, ensure_ascii=False)[:800]}")

    summary = {
        "server": str(SERVER),
        "python": sys.version,
        "tmp_workspace": str(tmp_ws),
        "passed": sum(1 for r in RESULTS if r["ok"]),
        "failed": sum(1 for r in RESULTS if not r["ok"]),
        "results": RESULTS,
    }
    (AUDIT_DIR / "mcp_conformance_result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== {summary['passed']} passed / {summary['failed']} failed -> mcp_conformance_result.json ===")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
