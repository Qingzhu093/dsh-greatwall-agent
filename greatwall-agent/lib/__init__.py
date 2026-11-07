"""
Great Wall Agent V4.2 — Pragmatic Core Engine & Antigravity MCP Backend
=======================================================================
精简务实的四大底层核心模块：
- sandbox.py   : 无 .git 清洁室快照导出、路径牢笼 (PathJail)、Windows Job Object 限额与五步墓碑回收
- archive.py   : 轻量级文件系统档案馆 (L0/L1/L2 按需索引、AST 原语提取、五件套遗产验收入库与撤回树)
- evaluator.py : AST 语法/结构改动/防泄漏检查、四元组剥皮查新与跨进程 HMAC 防伪评测收据
- engine.py    : 无人值守任务工作区生命周期编排器 (Phase 0 开局蒸馏锁死 -> 槽位分配 -> 四级分诊 -> 终局交付)
"""

from .sandbox import (
    CleanRoomSandbox,
    SandboxPathJail,
    force_cleanup_directory,
    run_bounded_subprocess,
)
from .archive import (
    LightweightArchive,
    LegacyValidationResult,
)
from .evaluator import (
    ASTCodeInspector,
    IsolatedEvaluator,
)
from .engine import (
    GreatWallEngine,
)

__all__ = [
    "CleanRoomSandbox",
    "SandboxPathJail",
    "force_cleanup_directory",
    "run_bounded_subprocess",
    "LightweightArchive",
    "LegacyValidationResult",
    "ASTCodeInspector",
    "IsolatedEvaluator",
    "GreatWallEngine",
]
__version__ = "4.2.0"
