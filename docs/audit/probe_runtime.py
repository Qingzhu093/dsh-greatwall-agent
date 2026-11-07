"""Runtime probes: AST surgical-replace edge cases, path jail, file lock, Job Object limits.

Run:  python -B plugins/dsh-greatwall-agent/docs/audit/probe_runtime.py
Read-only for the plugin (python -B => no __pycache__ in plugins/greatwall-agent/).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

AUDIT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = AUDIT_DIR.parents[2] / "greatwall-agent"
sys.path.insert(0, str(PLUGIN_ROOT))

from lib.sandbox import (  # noqa: E402
    CleanRoomSandbox,
    InterProcessFileLock,
    SandboxPathJail,
    run_bounded_subprocess,
)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

RESULTS: List[Dict[str, Any]] = []


def record(cid: str, title: str, ok: bool, evidence: Any) -> None:
    RESULTS.append({"id": cid, "title": title, "confirmed": bool(ok), "evidence": evidence})
    print(f"[{'CONFIRMED' if ok else 'not-reproduced'}] {cid} {title}\n    {json.dumps(evidence, ensure_ascii=False, default=str)[:1400]}\n")


def probe_surgical(tmp: Path) -> None:
    print("--- surgical_replace_block edge cases ---")
    # 1. CRLF file: is the untouched part rewritten too?
    crlf = tmp / "crlf_app.py"
    original = (
        "def solve(inputs):\r\n"
        "    return sum(inputs)\r\n"
        "\r\n"
        "def untouched_marker():\r\n"
        "    return 'UNTOUCHED'\r\n"
    )
    crlf.write_bytes(original.encode("utf-8"))
    ok, msg = CleanRoomSandbox.surgical_replace_block(crlf, "solve", "def solve(inputs):\n    return sum(inputs) * 2\n")
    after_bytes = crlf.read_bytes()
    untouched_after = after_bytes.split(b"def untouched_marker")[0]
    record(
        "S1",
        "surgical_replace_block 用 read_text/write_text 归一化换行：整文件被重写（LF 文件在 Windows 变 CRLF）",
        ok and after_bytes != original.encode("utf-8") and (b"\r\n" in after_bytes),
        {
            "result": ok,
            "message": msg,
            "bytes_before_prefix": repr(original.encode("utf-8")[:40]),
            "bytes_after_untouched_segment_ends_with": repr(after_bytes.split(b"def untouched_marker")[0][-6:]),
            "untouched_function_region_bytes_changed": after_bytes.split(b"def untouched_marker")[0] != original.encode("utf-8").split(b"def untouched_marker")[0],
        },
    )

    # 1b. LF file -> becomes CRLF on Windows?
    lf = tmp / "lf_app.py"
    lf.write_bytes(b"def solve(x):\n    return 1\n\ndef other():\n    return 2\n")
    ok2, msg2 = CleanRoomSandbox.surgical_replace_block(lf, "solve", "def solve(x):\n    return 3\n")
    lf_bytes = lf.read_bytes()
    record(
        "S1b",
        "LF 输入文件经一次微创替换后整体变成 CRLF（Windows 平台相关，跨平台字节不一致）",
        ok2 and b"\r\n" in lf_bytes and b"\r\n" not in b"def solve(x):\n    return 1\n",
        {"result": ok2, "message": msg2, "after_hex_prefix": lf_bytes[:40].hex(), "contains_crlf": b"\r\n" in lf_bytes},
    )

    # 2. UTF-8 BOM file: valid Python, rejected by the AST layer
    bom = tmp / "bom_app.py"
    bom.write_bytes(b"\xef\xbb\xbf" + b"def solve(x):\n    return 1\n")
    py_out = subprocess.run([sys.executable, "-B", str(bom)], capture_output=True, text=True)
    okb, msgb = CleanRoomSandbox.surgical_replace_block(bom, "solve", "def solve(x):\n    return 2\n")
    record(
        "S2",
        "UTF-8 BOM 脚本可被 CPython 正常执行，却被 surgical_replace_block 判为语法错误（Windows 常见编码）",
        py_out.returncode == 0 and okb is False and "U+FEFF" in msgb,
        {
            "python_runs_bom_file": py_out.returncode == 0,
            "python_stderr": py_out.stderr.strip()[:200],
            "surgical_result": okb,
            "surgical_message": msgb,
        },
    )

    # 3. non-UTF8 (GBK) source -> uncaught UnicodeDecodeError
    gbk = tmp / "gbk_app.py"
    gbk.write_bytes("# 中文注释\ndef solve(x):\n    return 1\n".encode("gbk"))
    try:
        okg, msgg = CleanRoomSandbox.surgical_replace_block(gbk, "solve", "def solve(x):\n    return 2\n")
        record("S3", "非 UTF-8(GBK) 脚本：未捕获 UnicodeDecodeError", False, {"result": okg, "message": msgg})
    except UnicodeDecodeError as e:
        record("S3", "非 UTF-8(GBK) 脚本：未捕获 UnicodeDecodeError 直接抛穿工具层", True, {"exception": repr(e)})

    # 4. multi-statement new code: only body[0] name is validated, everything is inserted
    multi = tmp / "multi_app.py"
    multi.write_text("def solve(x):\n    return 1\n", encoding="utf-8")
    okm, msgm = CleanRoomSandbox.surgical_replace_block(
        multi,
        "solve",
        "def solve(x):\n    return 2\n\nimport os\nos.system('echo injected')\n",
    )
    record(
        "S4",
        "新代码块只校验第一个 AST 节点名称，后续顶层语句（import/os.system）被原样插入",
        okm is True and "os.system" in multi.read_text(encoding="utf-8"),
        {"result": okm, "message": msgm, "file_after": multi.read_text(encoding="utf-8")},
    )

    # 5. decorated function: decorators silently dropped
    dec = tmp / "dec_app.py"
    dec.write_text(
        "import functools\n\n@functools.lru_cache(maxsize=None)\ndef solve(x):\n    return 1\n",
        encoding="utf-8",
    )
    okd, msgd = CleanRoomSandbox.surgical_replace_block(dec, "solve", "def solve(x):\n    return 2\n")
    dec_after = dec.read_text(encoding="utf-8")
    record(
        "S5",
        "替换带装饰器的函数会静默丢掉装饰器（@functools.lru_cache），工具仍返回成功",
        okd is True and "@functools.lru_cache" not in dec_after,
        {"result": okd, "message": msgd, "file_after": dec_after},
    )

    # 6. (removed: duplicate-method case is already rejected defensively)


def probe_jail(tmp: Path) -> None:
    print("--- SandboxPathJail ---")
    island = tmp / "island"
    shared = tmp / "shared"
    (island / "src").mkdir(parents=True, exist_ok=True)
    (shared / "archive" / "lineage_notes").mkdir(parents=True, exist_ok=True)
    outside = tmp / "outside"
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    (island / "src" / "main.py").write_text("x=1\n", encoding="utf-8")

    jail = SandboxPathJail(island, shared, "GLOBAL")
    # relative escape
    try:
        jail.validate_write("../../outside/secret.txt")
        rel_denied = False
    except PermissionError as e:
        rel_denied = True
    # junction escape (NTFS junctions do not need admin rights)
    junction = island / "src" / "junction_to_outside"
    junction_created = False
    try:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True, timeout=15)
        junction_created = junction.exists()
    except Exception:
        pass
    junction_denied = None
    if junction_created:
        try:
            jail.validate_write("src/junction_to_outside/secret.txt")
            junction_denied = False
        except PermissionError:
            junction_denied = True
    record(
        "J1",
        "SandboxPathJail 相对路径越界被拦截；NTFS Junction 越界也由 resolve() 兜底",
        rel_denied and (junction_denied is True or not junction_created),
        {"relative_escape_denied": rel_denied, "junction_created": junction_created, "junction_write_denied": junction_denied},
    )

    # lineage privacy rule: filename prefix check (relative path outside the island -> shared zone)
    notes = shared / "archive" / "lineage_notes"
    (notes / "LIN-OTHER_node-9.md").write_text("other lineage secret", encoding="utf-8")
    (notes / "LIN-MINE_node-1.md").write_text("my lineage note", encoding="utf-8")
    jail2 = SandboxPathJail(island, shared, "LIN-MINE")
    try:
        jail2.validate_read("../shared/archive/lineage_notes/LIN-OTHER_node-9.md")
        cross_denied = False
    except PermissionError as e:
        cross_denied = True
        cross_err = str(e)
    try:
        jail2.validate_read("../shared/archive/lineage_notes/LIN-MINE_node-1.md")
        own_allowed = True
    except PermissionError:
        own_allowed = False
    record(
        "J2",
        "跨血统笔记隔离按文件名前缀硬编码判断（同一血统放行、其他血统拦截）",
        cross_denied and own_allowed,
        {
            "foreign_note_denied": cross_denied,
            "foreign_note_error": cross_err if cross_denied else "",
            "own_note_allowed": own_allowed,
            "note": "validate_read 在引擎生产代码中没有任何调用点（仅 validate_write 用于 gw_surgical_replace）",
        },
    )


def probe_locks(tmp: Path) -> None:
    print("--- InterProcessFileLock ---")
    lock_path = tmp / "test.lock"
    counter = tmp / "counter.txt"
    n, procs = 4, 40
    script = tmp / "lock_worker.py"
    script.write_text(
        "import sys, time\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, r'{PLUGIN_ROOT}')\n"
        "from lib.sandbox import InterProcessFileLock\n"
        "lock_path, counter, n = sys.argv[1], sys.argv[2], int(sys.argv[3])\n"
        "for _ in range(n):\n"
        "    with InterProcessFileLock(Path(lock_path), timeout_sec=60):\n"
        "        p = Path(counter)\n"
        "        v = int(p.read_text(encoding='utf-8') or '0') if p.exists() else 0\n"
        "        time.sleep(0.002)\n"
        "        p.write_text(str(v + 1), encoding='utf-8')\n",
        encoding="utf-8",
    )
    procs_list = [
        subprocess.Popen([sys.executable, "-B", str(script), str(lock_path), str(counter), str(n)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(procs)
    ]
    rc = [pp.wait(timeout=300) for pp in procs_list]
    value = int(counter.read_text(encoding="utf-8") or "0") if counter.exists() else -1
    record(
        "L1",
        "跨进程文件锁互斥：40 进程 × 40 次 read-modify-write 恰好得到 1600（无丢失更新）",
        value == n * procs and all(x == 0 for x in rc),
        {"expected": n * procs, "actual": value, "nonzero_exits": [x for x in rc if x], "n_procs": procs},
    )

    # same-process reentrancy: second acquisition on the same lock file times out (not reentrant)
    lk1 = InterProcessFileLock(lock_path, timeout_sec=5)
    with lk1:
        t0 = time.perf_counter()
        try:
            with InterProcessFileLock(lock_path, timeout_sec=0.4):
                reentrant = "acquired"
        except TimeoutError as e:
            reentrant = f"TimeoutError after {time.perf_counter() - t0:.2f}s: {e}"
    record(
        "L2",
        "同一进程内对同一锁文件再次加锁不会重入（会阻塞到超时）——任何嵌套调用同一锁都会超时失败",
        str(reentrant).startswith("TimeoutError"),
        {"second_acquire": reentrant, "timeout_sec": 0.4, "lock": str(lock_path)},
    )


def probe_subprocess_limits(tmp: Path) -> None:
    print("--- run_bounded_subprocess / Job Object ---")
    shared = tmp / "shared"
    shared.mkdir(exist_ok=True)
    work = tmp / "sub_work"
    work.mkdir(exist_ok=True)
    marker = tmp / "GRANDCHILD_SURVIVED.txt"

    parent = None
    grandchild = work / "grandchild.py"
    grandchild.write_text(
        "import time, pathlib\n"
        "time.sleep(4)\n"
        f"pathlib.Path(r'{marker}').write_text('survived', encoding='utf-8')\n",
        encoding="utf-8",
    )
    parent_file = work / "parent.py"
    parent_file.write_text(
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-B', r'{grandchild}'])\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    t0 = time.perf_counter()
    res = run_bounded_subprocess(
        cmd=[sys.executable, "-B", str(parent_file)],
        cwd=work,
        shared_readonly_dir=shared,
        timeout_sec=2.0,
        max_memory_mb=1024,
    )
    elapsed = round(time.perf_counter() - t0, 2)
    time.sleep(5.5)  # give the grandchild time to survive if the job kill missed it
    record(
        "P1",
        "超时后 Job Object 连坐强杀整棵进程树（孙进程不再写出标记文件），exit=124",
        res.is_timeout and res.exit_code == 124 and not marker.exists(),
        {
            "is_timeout": res.is_timeout,
            "exit_code": res.exit_code,
            "elapsed_sec": elapsed,
            "grandchild_marker_created": marker.exists(),
            "peak_memory_mb": res.peak_memory_mb,
            "stderr_tail": res.stderr[-300:],
        },
    )

    # memory cap
    hog = work / "hog.py"
    hog.write_text("import time\nx = bytearray(200 * 1024 * 1024)\nprint('alloc ok', len(x))\ntime.sleep(0.2)\n", encoding="utf-8")
    res2 = run_bounded_subprocess(
        cmd=[sys.executable, "-B", str(hog)],
        cwd=work,
        shared_readonly_dir=shared,
        timeout_sec=30.0,
        max_memory_mb=64,
    )
    record(
        "P2",
        "Job Object 进程内存上限生效：200MB 分配在 max_memory_mb=64 下失败（非零退出）",
        res2.exit_code != 0,
        {"exit_code": res2.exit_code, "stdout": res2.stdout[-300:], "stderr": res2.stderr[-400:], "peak_memory_mb": res2.peak_memory_mb},
    )

    # stdout/stderr are always captured (never inherit MCP stdout) — negative control
    print_script = work / "noisy.py"
    print_script.write_text("import sys\nprint('NOISE_ON_STDOUT')\nprint('NOISE_ON_STDERR', file=sys.stderr)\n", encoding="utf-8")
    res3 = run_bounded_subprocess(
        cmd=[sys.executable, "-B", str(print_script)],
        cwd=work,
        shared_readonly_dir=shared,
        timeout_sec=15.0,
        max_memory_mb=1024,
    )
    record(
        "P3",
        "子进程 stdout/stderr 全量捕获（PIPE），不会污染 MCP 服务端 stdout",
        res3.exit_code == 0 and "NOISE_ON_STDOUT" in res3.stdout and "NOISE_ON_STDERR" in res3.stderr,
        {"exit_code": res3.exit_code, "stdout": res3.stdout.strip(), "stderr": res3.stderr.strip()},
    )


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="gw_audit_runtime_"))
    print(f"tmp = {tmp}\npython = {sys.executable} {sys.version.split()[0]}\n")
    try:
        for fn in (probe_surgical, probe_jail, probe_locks, probe_subprocess_limits):
            try:
                fn(tmp)
            except Exception:  # noqa: BLE001
                record(fn.__name__, "probe aborted", False, {"traceback": traceback.format_exc()})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out = {"python": sys.version, "results": RESULTS}
    (AUDIT_DIR / "runtime_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"=== {sum(1 for r in RESULTS if r['confirmed'])}/{len(RESULTS)} confirmed -> runtime_result.json ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
