"""Minimal MCP stdio (newline-delimited JSON-RPC) probe client for the Great Wall server.

Audit helper — read-only against the original plugin. All workspaces it touches live
under %TEMP%; nothing is written into plugins/greatwall-agent/.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

AUDIT_DIR = Path(__file__).resolve().parent
PLUGINS_DIR = AUDIT_DIR.parents[2]          # .../plugins
ORIG_PLUGIN = PLUGINS_DIR / "greatwall-agent"
SERVER = ORIG_PLUGIN / "bin" / "gw_mcp_server.py"
HOOK_GATE = ORIG_PLUGIN / "bin" / "hook_gate.py"


class _Reader(threading.Thread):
    def __init__(self, stream, name: str) -> None:
        super().__init__(daemon=True)
        self.stream = stream
        self.name = name
        self.q: "queue.Queue[Optional[bytes]]" = queue.Queue()

    def run(self) -> None:
        try:
            while True:
                line = self.stream.readline()
                if not line:
                    break
                self.q.put(line)
        finally:
            self.q.put(None)


class MCPProc:
    """Spawns bin/gw_mcp_server.py and speaks newline-delimited JSON-RPC over stdio."""

    def __init__(self, extra_env: Optional[Dict[str, str]] = None, server: Optional[Path] = None,
                 cwd: Optional[Path] = None) -> None:
        env = os.environ.copy()
        env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
        if extra_env:
            env.update(extra_env)
        self.server = server or SERVER
        # NEVER let the server inherit the repo as its cwd: gw_mcp_server.py:330 falls back to
        # os.getcwd() when workspaceRoot is missing, which would materialise a runtime workspace
        # next to the audit evidence.
        self.cwd = Path(cwd) if cwd else Path(tempfile.mkdtemp(prefix="gw_audit_servercwd_"))
        self.proc = subprocess.Popen(
            [sys.executable, "-B", str(self.server)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.cwd),
            env=env,
        )
        self.out = _Reader(self.proc.stdout, "stdout")  # type: ignore[arg-type]
        self.err = _Reader(self.proc.stderr, "stderr")  # type: ignore[arg-type]
        self.out.start()
        self.err.start()
        self.raw_out: List[bytes] = []
        self.raw_err: List[bytes] = []

    # -- low level -------------------------------------------------------
    def send_raw(self, data: bytes) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def send(self, obj: Any) -> None:
        self.send_raw(json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n")

    def read_line(self, timeout: float = 10.0) -> Optional[bytes]:
        try:
            line = self.out.q.get(timeout=timeout)
        except queue.Empty:
            return b"<TIMEOUT>"
        if line is None:
            return None
        self.raw_out.append(line)
        return line

    def drain_stderr(self, timeout: float = 0.4) -> List[bytes]:
        got: List[bytes] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = self.err.q.get(timeout=max(0.01, deadline - time.time()))
            except queue.Empty:
                break
            if line is None:
                break
            self.raw_err.append(line)
            got.append(line)
        return got

    # -- protocol helpers ------------------------------------------------
    def rpc(self, req_id: Any, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 15.0) -> Dict[str, Any]:
        req: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            req["params"] = params
        self.send(req)
        raw = self.read_line(timeout=timeout)
        if raw is None:
            return {"_raw": None, "_eof": True}
        if raw == b"<TIMEOUT>":
            return {"_raw": "<TIMEOUT>"}
        return {"_raw": raw, "json": json.loads(raw.decode("utf-8"))}

    def call_tool(self, name: str, arguments: Dict[str, Any], req_id: Any = 1, timeout: float = 180.0) -> Dict[str, Any]:
        return self.rpc(req_id, "tools/call", {"name": name, "arguments": arguments}, timeout=timeout)

    def initialize(self) -> Dict[str, Any]:
        r = self.rpc(1, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "gw-audit", "version": "1.0"},
        })
        # notification: no id, no response expected
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return r

    def close(self, timeout: float = 10.0) -> Tuple[Optional[int], List[bytes]]:
        try:
            assert self.proc.stdin is not None
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            rc = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            rc = self.proc.wait(timeout=5)
        stderr_tail: List[bytes] = []
        try:
            while True:
                line = self.err.q.get(timeout=0.2)
                if line is None:
                    break
                stderr_tail.append(line)
        except queue.Empty:
            pass
        return rc, stderr_tail

    def kill(self) -> None:
        try:
            self.proc.kill()
        except Exception:
            pass


def tool_result_payload(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the JSON payload embedded in a tools/call content[0].text, if any."""
    try:
        return json.loads(resp["json"]["result"]["content"][0]["text"])
    except Exception:
        return {}


def is_error_result(resp: Dict[str, Any]) -> Optional[bool]:
    try:
        return bool(resp["json"]["result"]["isError"])
    except Exception:
        return None
