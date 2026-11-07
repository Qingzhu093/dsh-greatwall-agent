#!/usr/bin/env python3
"""
Great Wall Agent V4.2 — Lightweight PreToolUse Hook Gate (`hook_gate.py`)
========================================================================
原则：克制、精准、零误伤（绝不在非长城攻关工作区瞎拦任何命令！）。
仅当检测到当前调用涉及长城攻关工作区敏感目录（`.kernel_vault`、`shared_readonly`、`worktrees/slot_`）时生效：
1. 拦截对 `.kernel_vault` 的任何读取或篡改；
2. 拦截对 `shared_readonly/` 公共只读区的文件写入或终端重定向篡改；
3. 拦截跨孤岛偷看隔壁 `worktrees/slot_*` 分支代码（如 `../slot_` 或同时引用两个不同槽位）。
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict


def evaluate_hook(payload: Dict[str, Any]) -> Dict[str, Any]:
    tool_call = payload.get("toolCall") or {}
    tool_name = str(tool_call.get("name", ""))
    tool_args = tool_call.get("args") or {}

    target_path_str = str(tool_args.get("Path") or tool_args.get("TargetFile") or "")
    cmd_line = str(tool_args.get("CommandLine") or "")
    combined_text = f"{target_path_str} {cmd_line}".replace("\\", "/")

    # 快速放行：若完全未涉及长城工作区敏感目录名，0.1ms 直接 allow！
    if not any(kw in combined_text for kw in (".kernel_vault", "shared_readonly", "worktrees/slot_", "../slot_")):
        return {"decision": "allow"}

    # 1. 拦截探索节点直接通过文件工具或终端命令偷看 `.kernel_vault` 特权保险箱
    if ".kernel_vault" in combined_text:
        return {
            "decision": "deny",
            "reason": "🔒 [长城 Agent 清洁室隔离门禁] 严禁直接读取或修改 `.kernel_vault` 内核保险箱（含评测真值与 HMAC 密钥）！请使用 `gw_*` 标准 MCP 工具交互。",
        }

    # 2. 拦截对 `shared_readonly` 公共只读区执行文件写入或命令行重定向篡改
    if "shared_readonly" in combined_text:
        if tool_name in ("write_file", "edit_file", "replace_file_content", "multi_replace_file_content"):
            return {
                "decision": "deny",
                "reason": "🔒 [长城 Agent 只读档案馆门禁] `shared_readonly/` 为公共只读挂载区，严禁直接用写文件工具篡改！请在孤岛 `legacy_out/` 下提交遗产包并通过 `gw_submit_legacy` 验收入库。",
            }
        if tool_name == "run_command":
            write_shell_patterns = (
                r">", r"\bOut-File\b", r"\bSet-Content\b", r"\bAdd-Content\b",
                r"\bRemove-Item\b", r"\brm\s", r"\bdel\s", r"\bmv\s", r"\bMove-Item\b",
            )
            if any(re.search(pat, cmd_line, re.IGNORECASE) for pat in write_shell_patterns):
                return {
                    "decision": "deny",
                    "reason": "🔒 [长城 Agent 只读档案馆门禁] 严禁通过终端命令重定向或修改 `shared_readonly/` 公共只读区！",
                }

    # 3. 拦截跨槽位偷看隔壁孤岛 (`../slot_` 或同一命令中出现两个不同的 `slot_xx_node_yy`)
    if "../slot_" in combined_text:
        return {
            "decision": "deny",
            "reason": "🔒 [长城 Agent 跨孤岛防偷看门禁] 严禁通过 `../slot_*` 越界访问其他并行探索槽位的私有目录！",
        }
    referenced_slots = set(re.findall(r"worktrees/(slot_[a-zA-Z0-9_-]+)", combined_text))
    if len(referenced_slots) > 1:
        return {
            "decision": "deny",
            "reason": f"🔒 [长城 Agent 跨孤岛防偷看门禁] 检测到单次操作同时引用多个孤岛槽位 {sorted(referenced_slots)}，严禁跨槽位偷看或拷贝未验收入库的半成品代码！",
        }

    return {"decision": "allow"}


def main() -> None:
    try:
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        raw = sys.stdin.read()
        if not raw.strip():
            sys.stdout.write('{"decision": "allow"}\n')
            return
        payload = json.loads(raw)
        out = evaluate_hook(payload)
        sys.stdout.write(json.dumps(out, ensure_ascii=True) + "\n")
        sys.stdout.flush()
    except Exception:
        sys.stdout.write('{"decision": "allow"}\n')
        sys.stdout.flush()


if __name__ == "__main__":
    main()
