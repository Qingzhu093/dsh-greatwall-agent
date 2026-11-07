"""
AST Forensic Inspector, De-Jargonized Novelty Stripper, Cross-Branch Differential Tester & HMAC Isolated Evaluator.
严格对齐《15_长城Agent_V4无人值守架构与沙箱工程实战规范.md》第 2、4、5、7、8 章：
1. ASTCodeInspector：
   - 扫描逃逸黑客调用 (ctypes/socket/urllib/inspect.stack) 与超大硬编码查表作弊；
   - 强制执行 Phase 0 蒸馏契约：拦截《过时模型黑名单》(obsolete_familiarity_blacklist) 与禁止重复造轮子函数 (如手搓 def k_fold / train_test_split)；
   - 执行 MLE-STAR 式多模态数据源完整性检查 (A_data) 与防数据穿越泄漏扫描 (切分前 fit_transform / concat([train, test]))；
   - 计算剥离常数与变量名后的 AST 结构改动率 + 识别三大常见偷懒陷阱 (定性画图逃避、静态代理逃避、超参微调伪装)；
   - 核对“方案说明与实际代码一致性” (专治宣称探索 e in {2,3,4,5} 实际写死 e=2)；
   - 提取 `archive.ledger.primitives.*` 的跨血统调用列表，支撑原语跨血统引用真实统计；
   - 四元组数学算子剥皮查新与《教科书常识黑名单》比对。
2. IsolatedEvaluator：
   - 跨进程物理隔离运行 + 同构扰动测试 (Isomorphic Perturbation) + 一次性随机盐值 (run_nonce) HMAC-SHA256 签名成绩单；
   - 跨分支差分互测 (Cross-Branch Differential Testing, §7.4)：无需真值标签，用极端边界输入对撞两条正交分支，暴露分歧算例；
   - 错题热勘误与历史分数追溯重算 (Retroactive Errata & Branch Revival, §7.3.2)：剔除生成器 Bug 错题并自动平反被误杀分支。
"""

from __future__ import annotations

import ast
import hashlib
import hmac
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .sandbox import InterProcessFileLock, run_bounded_subprocess


DEFAULT_TEXTBOOK_COMMONSENSE: List[str] = [
    "mini-batch", "micro-batch", "microbatch", "gradient accumulation",
    "l1 regularization", "l2 regularization", "weight decay", "dropout",
    "cosine annealing", "reducelronplateau", "step decay", "adaptive learning rate",
    "hybrid matrix factorization", "svd", "standard pruning", "int8 quantization",
    "k-fold cross validation", "grid search", "random search", "standard scaler",
]

FORBIDDEN_WHEEL_REINVENTION_DEFS: Set[str] = {
    "k_fold", "kfold", "stratified_kfold", "group_kfold", "train_test_split",
    "kd_tree", "kdtree", "quick_sort", "merge_sort",
}


@dataclass
class ASTInspectionReport:
    passed: bool
    security_violations: List[str] = field(default_factory=list)
    contract_violations: List[str] = field(default_factory=list)
    leakage_warnings: List[str] = field(default_factory=list)
    unreferenced_modalities: List[str] = field(default_factory=list)
    attractor_traps_detected: List[str] = field(default_factory=list)
    imported_archive_primitives: List[str] = field(default_factory=list)
    structural_diff_ratio: float = 1.0
    is_superficial_tweak: bool = False
    claim_code_mismatch: List[str] = field(default_factory=list)
    novelty_classification: str = "SOLID_ENGINEERING"
    novelty_notes: str = ""
    stripped_operator_tuple: Dict[str, str] = field(default_factory=dict)


class ASTCodeInspector:
    """轻量零开销的 Python AST 静态审计器（毫秒级完成全套反作弊、蒸馏契约对齐与真伪创新对账）"""

    FORBIDDEN_IMPORTS = {
        "ctypes", "winreg", "socket", "urllib", "requests", "http", "ftplib", "telnetlib", "webbrowser"
    }
    FORBIDDEN_CALLS = {
        "eval", "exec", "__subclasses__", "_getframe"
    }

    @classmethod
    def inspect_code(
        cls,
        candidate_code: str,
        parent_code: str = "",
        claimed_swept_variables: Optional[List[str]] = None,
        operator_description: str = "",
        commonsense_blacklist: Optional[List[str]] = None,
        obsolete_blacklist: Optional[List[str]] = None,
        required_data_modalities: Optional[List[str]] = None,
        enforce_data_completeness: bool = False,
        max_lookup_table_size: int = 40,
    ) -> ASTInspectionReport:
        report = ASTInspectionReport(passed=True)
        try:
            tree = ast.parse(candidate_code)
        except SyntaxError as e:
            report.passed = False
            report.security_violations.append(f"SyntaxError: {e}")
            return report

        imported_primitives: Set[str] = set()
        uses_plotting_libs = False
        called_functions: Set[str] = set()
        defined_functions: Set[str] = set()

        # 1. 安全逃逸、硬编码查表、手搓基础轮子与档案馆原语引用扫描
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined_functions.add(node.name)
                if node.name.lower() in FORBIDDEN_WHEEL_REINVENTION_DEFS:
                    report.contract_violations.append(
                        f"违反《调库 vs 造轮子契约》：检测到手搓基础工具函数 `def {node.name}()` (第 {node.lineno} 行)，请直接调用标准库或 sklearn/scipy 原生实现！"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    top_pkg = alias.name.split(".")[0]
                    if top_pkg in cls.FORBIDDEN_IMPORTS:
                        report.security_violations.append(f"禁止导入外部网络/底层逃逸库: '{alias.name}' (第 {node.lineno} 行)")
                    if top_pkg in ("matplotlib", "seaborn", "plotly"):
                        uses_plotting_libs = True
                    if alias.name.startswith("archive.ledger.primitives."):
                        prim_mod = alias.name.split("archive.ledger.primitives.", 1)[1].split(".")[0]
                        if prim_mod:
                            imported_primitives.add(prim_mod)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_pkg = node.module.split(".")[0]
                if top_pkg in cls.FORBIDDEN_IMPORTS:
                    report.security_violations.append(f"禁止从受限模块导入: '{node.module}' (第 {node.lineno} 行)")
                if top_pkg in ("matplotlib", "seaborn", "plotly"):
                    uses_plotting_libs = True
                if node.module.startswith("archive.ledger.primitives"):
                    parts = node.module.split(".")
                    if len(parts) >= 4:
                        imported_primitives.add(parts[3])
                    else:
                        for alias in node.names:
                            if alias.name != "*":
                                imported_primitives.add(alias.name)
            elif isinstance(node, ast.Call):
                fn_name = ""
                if isinstance(node.func, ast.Name):
                    fn_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    fn_name = node.func.attr
                if fn_name:
                    called_functions.add(fn_name)
                if fn_name in cls.FORBIDDEN_CALLS:
                    report.security_violations.append(f"禁止调用动态反射/执行函数: '{fn_name}()' (第 {node.lineno} 行)")
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    if node.func.value.id == "inspect" and node.func.attr in ("stack", "currentframe"):
                        report.security_violations.append(f"禁止调用栈反射探测: 'inspect.{node.func.attr}()' (第 {node.lineno} 行)")
            elif isinstance(node, ast.Dict):
                if len(node.keys) > max_lookup_table_size and all(
                    isinstance(v, ast.Constant) for v in node.values if v is not None
                ):
                    report.security_violations.append(
                        f"检测到疑似硬编码查表作弊字典 (含 {len(node.keys)} 个常量键值对，第 {node.lineno} 行)"
                    )

        report.imported_archive_primitives = sorted(imported_primitives)

        # 2. 检查 Phase 0《过时模型黑名单》(Familiarity Bias Blacklist)
        if obsolete_blacklist:
            for item in obsolete_blacklist:
                # 提取黑名单条目中的核心标识符（例如 "LogisticRegression" 或 "ResNet18"）
                tokens = [
                    tok.strip()
                    for tok in re.split(r"[/(),\s]+", item)
                    if len(tok.strip()) >= 4 and tok.strip()[0].isupper()
                ]
                for tok in tokens:
                    if re.search(rf"\b{re.escape(tok)}\b", candidate_code):
                        report.contract_violations.append(
                            f"违反 Phase 0《反预训练偏见黑名单》：代码中违规使用了已被禁用的陈旧方案 '{tok}' (对应黑名单项: '{item}')"
                        )
                        break

        # 3. 检查 MLE-STAR 多模态数据源完整性 (A_data 哨兵)
        if required_data_modalities:
            for mod_file in required_data_modalities:
                basename = Path(mod_file).name
                stem = Path(mod_file).stem
                if basename not in candidate_code and stem not in candidate_code:
                    report.unreferenced_modalities.append(mod_file)
            if report.unreferenced_modalities and enforce_data_completeness:
                report.contract_violations.append(
                    f"违反多模态数据完整性红线 (A_data)：脚本遗漏了公共数据集中的以下模态文件 {report.unreferenced_modalities}，严禁只挑单一简单表训练！"
                )

        # 4. MLE-STAR 式数据防泄漏静态扫描
        has_cv_or_split = any(
            kw in candidate_code for kw in ("KFold", "Split", "train_test_split", "cross_val", "train_idx")
        )
        if "fit_transform(" in candidate_code and not has_cv_or_split:
            report.leakage_warnings.append(
                "检测到调用 `.fit_transform()` 但脚本中未出现训练/验证集切分 (KFold/Split)，存在全量统计量数据穿越泄漏风险！"
            )
        if re.search(r"concat\s*\(\s*\[\s*train.*test", candidate_code, re.IGNORECASE):
            report.leakage_warnings.append(
                "检测到疑似将训练集与测试集 `concat([train, test])` 合并预处理，严禁测试集特征统计量穿透！"
            )

        # 5. 计算剥离常数后的 AST 计算图结构改动率 + 三大常见偷懒陷阱检测 (§7.6.2)
        if parent_code.strip():
            report.structural_diff_ratio = cls.compute_structural_diff_ratio(parent_code, candidate_code)
            if report.structural_diff_ratio < 0.015 and candidate_code.strip() != parent_code.strip():
                report.is_superficial_tweak = True

        if uses_plotting_libs and report.is_superficial_tweak:
            report.attractor_traps_detected.append(
                "QUALITATIVE_VISUALIZATION_TRAP: 核心计算图结构零改动 (<1.5%)，仅新增画图可视化逻辑逃避硬指标攻坚！"
            )

        # 6. 方案说明与代码 AST 一致性对账 (专治 Sakana 实测中宣称动态探索 e in {2,3,4,5} 实际写死 e = 2)
        if claimed_swept_variables:
            for var_name in claimed_swept_variables:
                if not cls._verify_variable_is_dynamic(tree, var_name):
                    report.claim_code_mismatch.append(
                        f"声明-代码对账失败：声称对控制变量 '{var_name}' 进行了动态探索/消融，但 AST 中该变量仅被赋值为单一静态常量或根本未参与循环控制流！"
                    )

        # 7. 四元组数学算子剥皮查新与《教科书常识黑名单》比对 (§4.2 & §8.1 #8)
        report.stripped_operator_tuple = cls.extract_operator_four_tuple(tree, operator_description)
        if operator_description.strip():
            classification, note = cls.evaluate_stripped_novelty(
                operator_description, commonsense_blacklist or DEFAULT_TEXTBOOK_COMMONSENSE
            )
            report.novelty_classification = classification
            report.novelty_notes = note
            if report.is_superficial_tweak and classification == "NOVEL_METHODOLOGY":
                report.novelty_classification = "HYPERPARAMETER_TWEAK"
                report.novelty_notes = "AST 结构改动率 < 1.5%（仅修改常数字面量），已自动从方法创新降级为超参微调。"
                report.attractor_traps_detected.append(
                    "HYPERPARAMETER_GRID_DISGUISE: 仅修改常数字面量却自封方法学创新，已强制降级为 HYPERPARAMETER_TWEAK。"
                )

        if report.security_violations or report.contract_violations or report.claim_code_mismatch:
            report.passed = False

        return report

    @staticmethod
    def extract_operator_four_tuple(tree: ast.AST, operator_description: str = "") -> Dict[str, str]:
        """从 AST 与描述中提取去修辞化的四元数学表征 (input, operator, objective, complexity)"""
        func_names = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        calls = sorted({
            (n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id)
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))
        })[:12]
        loop_depth = 0
        for n in ast.walk(tree):
            if isinstance(n, (ast.For, ast.While)):
                sub_loops = sum(1 for c in ast.walk(n) if isinstance(c, (ast.For, ast.While)))
                loop_depth = max(loop_depth, sub_loops)
        est_complexity = "O(1)/Vectorized" if loop_depth == 0 else (f"O(N^{loop_depth})" if loop_depth > 1 else "O(N)")
        return {
            "input": f"functions={func_names[:5]}",
            "operator": operator_description.strip()[:120] or f"ast_calls={calls}",
            "objective": "optimize_primary_metric",
            "complexity": est_complexity,
        }

    @staticmethod
    def _skeletonize_ast(source_code: str) -> List[str]:
        """剥离所有注释、变量名与数值/字符串常量，仅保留 AST 语法结构与控制流/函数调用骨架"""
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []
        tokens: List[str] = []
        for node in ast.walk(tree):
            tname = type(node).__name__
            if isinstance(node, (ast.Constant, ast.Name)):
                tokens.append(tname)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    tokens.append(f"Call:{node.func.attr}")
                elif isinstance(node.func, ast.Name):
                    tokens.append(f"Call:{node.func.id}")
                else:
                    tokens.append("Call")
            else:
                tokens.append(tname)
        return tokens

    @classmethod
    def compute_structural_diff_ratio(cls, code_a: str, code_b: str) -> float:
        """计算两段代码的 AST 拓扑骨架差异率 [0.0, 1.0]（纯改数字或变量名时差异率为 0.0）"""
        skel_a = cls._skeletonize_ast(code_a)
        skel_b = cls._skeletonize_ast(code_b)
        if not skel_a and not skel_b:
            return 0.0
        if skel_a == skel_b:
            return 0.0

        counts_a: Dict[str, int] = {}
        counts_b: Dict[str, int] = {}
        for t in skel_a:
            counts_a[t] = counts_a.get(t, 0) + 1
        for t in skel_b:
            counts_b[t] = counts_b.get(t, 0) + 1

        all_keys = set(counts_a) | set(counts_b)
        diff_sum = sum(abs(counts_a.get(k, 0) - counts_b.get(k, 0)) for k in all_keys)
        total_sum = max(1, len(skel_a) + len(skel_b))
        return round(min(1.0, diff_sum / total_sum), 4)

    @staticmethod
    def _verify_variable_is_dynamic(tree: ast.AST, var_name: str) -> bool:
        """检查变量 `var_name` 是否真实作为函数参数、循环迭代变量或列表/集合遍历被动态使用，而非死写成单一常数"""
        used_in_loop_or_param = False
        constant_assignments = 0
        non_constant_assignments = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.arg) and node.arg == var_name:
                used_in_loop_or_param = True
            elif isinstance(node, ast.For):
                if var_name in ast.unparse(node.target) or var_name in ast.unparse(node.iter):
                    used_in_loop_or_param = True
            elif isinstance(node, ast.comprehension):
                if var_name in ast.unparse(node.target) or var_name in ast.unparse(node.iter):
                    used_in_loop_or_param = True
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == var_name:
                        if isinstance(node.value, ast.Constant):
                            constant_assignments += 1
                        else:
                            non_constant_assignments += 1

        if used_in_loop_or_param or non_constant_assignments > 0:
            return True
        if constant_assignments > 1:
            return True
        return False

    @staticmethod
    def evaluate_stripped_novelty(operator_description: str, commonsense_blacklist: List[str]) -> Tuple[str, str]:
        """
        剥离花哨包装形容词，检查底层算子描述是否落入《教科书常识黑名单》：
        若命中微批处理、L1/L2 正则、标准剪枝等常识项，仅准标记为 `BASELINE_ENGINEERING`，严禁自封 `NOVEL_METHODOLOGY`。
        """
        buzzwords = [
            r"green-aware", r"eco-friendly", r"quantum-inspired", r"hyper-adaptive",
            r"multi-granular", r"synergistic", r"holistic", r"paradigm-shifting",
            r"全息", r"量子启发", r"超维自适应", r"生态感知", r"颠覆性",
        ]
        stripped = operator_description.lower()
        for bw in buzzwords:
            stripped = re.sub(bw, "", stripped, flags=re.IGNORECASE)

        matched_commonsense = [item for item in commonsense_blacklist if item.lower() in stripped]
        if matched_commonsense:
            return (
                "BASELINE_ENGINEERING",
                f"算子剥皮比对命中《教科书常识黑名单》({', '.join(matched_commonsense)})，归类为常规工程调优，禁止在报告中吹嘘为方法创新。",
            )
        return ("NOVEL_METHODOLOGY", "底层算子结构未命中教科书常识黑名单，准许作为方法学创新候选。")


# ============================================================================
# 2. 跨进程 HMAC 防伪隔离评测器、跨分支差分互测与错题热勘误器 (IsolatedEvaluator)
# ============================================================================

class IsolatedEvaluator:
    """
    跨进程黑盒评测与四级分诊裁决器：
    1. 每次评测生成一次性随机盐值 `run_nonce`；
    2. 自动加载 `distilled/sota_anchors.json` 与 `task_config.yaml`，执行 AST 契约与多模态数据完整性审计；
    3. 在受限子进程中执行候选脚本与评测基准（含常规 Frozen 集、Live 挑战集、同构旋转/重排扰动测试与逐算例得分记录）；
    4. 使用内核专属密钥 `.kernel_vault/hmac_secret.key` 对 `(node_id, commit_hash, run_nonce, frozen_score, live_score)`
       计算 HMAC-SHA256 防伪签名，杜绝节点伪造静态 `metrics_receipt.json`；
    5. 支持跨分支差分互测 (`run_differential_test`, §7.4) 与错题热勘误追溯平反 (`deprecate_errata_case`, §7.3.2)。
    """

    def __init__(self, vault_dir: Path, shared_readonly_dir: Path) -> None:
        self.vault_dir = vault_dir.resolve()
        self.shared_readonly_dir = shared_readonly_dir.resolve()
        self.secret_file = self.vault_dir / "hmac_secret.key"
        self.eval_suite_dir = self.vault_dir / "evaluator_suite"
        self.receipts_history_file = self.eval_suite_dir / "receipts_history.jsonl"
        self.errata_file = self.eval_suite_dir / "errata_registry.json"
        self.eval_suite_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_secret()

    def _ensure_secret(self) -> bytes:
        if not self.secret_file.exists():
            self.secret_file.write_text(uuid.uuid4().hex + uuid.uuid4().hex, encoding="utf-8")
        return self.secret_file.read_text(encoding="utf-8").strip().encode("utf-8")

    def sign_receipt(self, node_id: str, commit_hash: str, run_nonce: str, frozen_score: float, live_score: float) -> str:
        secret = self._ensure_secret()
        payload = f"{node_id}|{commit_hash}|{run_nonce}|{frozen_score:.8f}|{live_score:.8f}".encode("utf-8")
        return hmac.new(secret, payload, hashlib.sha256).hexdigest()

    def verify_receipt_signature(self, receipt: Dict[str, Any]) -> bool:
        try:
            expected = self.sign_receipt(
                node_id=str(receipt["node_id"]),
                commit_hash=str(receipt["commit_hash"]),
                run_nonce=str(receipt["run_nonce"]),
                frozen_score=float(receipt["scores"]["frozen_benchmark"]),
                live_score=float(receipt["scores"]["live_challenge"]),
            )
            return hmac.compare_digest(expected, str(receipt.get("hmac_sha256_signature", "")))
        except Exception:
            return False

    def _load_distilled_contracts(self) -> Tuple[List[str], List[str], List[str]]:
        """读取 Phase 0 固化的过时模型黑名单、常识黑名单与多模态数据清点表"""
        obsolete_list: List[str] = []
        commonsense_list: List[str] = list(DEFAULT_TEXTBOOK_COMMONSENSE)
        data_modalities: List[str] = []

        sota_path = self.shared_readonly_dir / "distilled" / "sota_anchors.json"
        if sota_path.exists():
            try:
                sdata = json.loads(sota_path.read_text(encoding="utf-8"))
                obsolete_list = sdata.get("obsolete_familiarity_blacklist", [])
                commonsense_list = sdata.get("trivial_commonsense_blacklist", commonsense_list)
            except Exception:
                pass

        task_cfg_path = self.shared_readonly_dir / "task_config.yaml"
        if task_cfg_path.exists():
            try:
                tdata = json.loads(task_cfg_path.read_text(encoding="utf-8"))
                data_modalities = tdata.get("data_completeness_inventory", [])
            except Exception:
                pass

        return obsolete_list, commonsense_list, data_modalities

    def evaluate_island(
        self,
        island_dir: Path,
        node_id: str,
        commit_hash: str,
        entry_script: str = "src/main.py",
        parent_code: str = "",
        anchor_s0_score: float = 0.0,
        higher_is_better: bool = True,
        timeout_sec: float = 120.0,
        claimed_swept_variables: Optional[List[str]] = None,
        operator_description: str = "",
        enforce_data_completeness: bool = False,
    ) -> Dict[str, Any]:
        """
        执行端到端防作弊沙箱评测并生成签名收据 `legacy_out/metrics_receipt.json`
        """
        script_path = island_dir / entry_script
        if not script_path.exists():
            return {
                "status": "ERROR",
                "triage_tier": "IN_PLACE_REPAIR",
                "message": f"找不到入口脚本: {script_path}",
            }

        candidate_code = script_path.read_text(encoding="utf-8")
        obsolete_list, commonsense_list, data_modalities = self._load_distilled_contracts()

        # 1. AST 静态安全、蒸馏契约、防泄漏与结构改动对账
        ast_report = ASTCodeInspector.inspect_code(
            candidate_code=candidate_code,
            parent_code=parent_code,
            claimed_swept_variables=claimed_swept_variables,
            operator_description=operator_description,
            commonsense_blacklist=commonsense_list,
            obsolete_blacklist=obsolete_list,
            required_data_modalities=data_modalities,
            enforce_data_completeness=enforce_data_completeness,
        )
        if not ast_report.passed:
            return {
                "status": "REJECTED_BY_AST_AUDITOR",
                "triage_tier": "DEAD_END_ARCHIVE",
                "security_violations": ast_report.security_violations,
                "contract_violations": ast_report.contract_violations,
                "claim_code_mismatch": ast_report.claim_code_mismatch,
                "leakage_warnings": ast_report.leakage_warnings,
                "unreferenced_modalities": ast_report.unreferenced_modalities,
            }

        # 2. 跨进程隔离运行评测器
        run_nonce = str(uuid.uuid4())
        custom_eval_runner = self.eval_suite_dir / "evaluate_runner.py"
        deprecated_cases = self.get_deprecated_cases()

        if custom_eval_runner.exists():
            cmd = [
                sys.executable,
                str(custom_eval_runner),
                "--candidate-script",
                str(script_path.resolve()),
                "--island-dir",
                str(island_dir.resolve()),
                "--run-nonce",
                run_nonce,
            ]
        else:
            harness_code = self._build_builtin_eval_harness(str(script_path.resolve()), run_nonce, deprecated_cases)
            cmd = [sys.executable, "-c", harness_code]

        sub_res = run_bounded_subprocess(
            cmd=cmd,
            cwd=island_dir,
            shared_readonly_dir=self.shared_readonly_dir,
            timeout_sec=timeout_sec,
            max_memory_mb=8192,
        )

        if sub_res.exit_code != 0:
            err_snippet = (sub_res.stderr or sub_res.stdout).strip()[-600:]
            return {
                "status": "RUNTIME_CRASH",
                "triage_tier": "IN_PLACE_REPAIR",
                "exit_code": sub_res.exit_code,
                "is_timeout": sub_res.is_timeout,
                "wall_time_sec": sub_res.wall_time_sec,
                "peak_memory_mb": sub_res.peak_memory_mb,
                "error_traceback": err_snippet,
                "recommended_action": "保留当前孤岛目录，根据 error_traceback 原地微创修复报错代码段（最多允许 3 步快速修补）。",
            }

        parsed_metrics = self._extract_metrics_from_stdout(sub_res.stdout)
        case_scores: Dict[str, float] = parsed_metrics.get("case_scores", {}) if isinstance(parsed_metrics.get("case_scores"), dict) else {}

        # 若返回了逐算例得分且存在被勘误废弃的错题，自动剔除废弃算例后计算均分
        if case_scores:
            valid_vals = [float(v) for k, v in case_scores.items() if k not in deprecated_cases]
            computed_live = sum(valid_vals) / len(valid_vals) if valid_vals else float(parsed_metrics.get("live_score", 0.0))
        else:
            computed_live = float(parsed_metrics.get("live_score", parsed_metrics.get("frozen_score", 0.0)))

        frozen_score = float(parsed_metrics.get("frozen_score", computed_live))
        live_score = computed_live
        iso_gap = float(parsed_metrics.get("isomorphic_perturbation_gap", 0.0))
        niche_score = float(parsed_metrics.get("niche_hard_cases_score", live_score))

        # 3. 同构变换扰动防背题检验
        if iso_gap > 0.05:
            return {
                "status": "REJECTED_INDEX_MEMORIZATION",
                "triage_tier": "DEAD_END_ARCHIVE",
                "isomorphic_perturbation_gap": iso_gap,
                "message": f"同构打乱/旋转算例前后得分差高达 {iso_gap:.4f} (> 0.05)，判定为针对固定算例顺序硬编码背答案！",
            }

        # 4. 四级分诊裁决 (4-Tier Triage)
        triage_tier = self._determine_triage_tier(
            frozen_score=frozen_score,
            niche_score=niche_score,
            anchor_s0_score=anchor_s0_score,
            higher_is_better=higher_is_better,
        )

        # 5. 签发带 HMAC-SHA256 签名的防伪成绩单收据
        sig = self.sign_receipt(node_id, commit_hash, run_nonce, frozen_score, live_score)
        receipt = {
            "receipt_id": f"RCPT-{int(time.time())}-{node_id}",
            "node_id": node_id,
            "commit_hash": commit_hash,
            "run_nonce": run_nonce,
            "hmac_sha256_signature": sig,
            "triage_tier": triage_tier,
            "scores": {
                "frozen_benchmark": round(frozen_score, 6),
                "live_challenge": round(live_score, 6),
                "isomorphic_perturbation_gap": round(iso_gap, 6),
                "niche_hard_cases_score": round(niche_score, 6),
            },
            "case_scores": case_scores,
            "resource_profile": {
                "wall_time_sec": sub_res.wall_time_sec,
                "peak_memory_mb": sub_res.peak_memory_mb,
            },
            "ast_audit": {
                "structural_diff_ratio": ast_report.structural_diff_ratio,
                "is_superficial_tweak": ast_report.is_superficial_tweak,
                "data_leakage_clean": len(ast_report.leakage_warnings) == 0,
                "leakage_warnings": ast_report.leakage_warnings,
                "unreferenced_modalities": ast_report.unreferenced_modalities,
                "attractor_traps_detected": ast_report.attractor_traps_detected,
                "imported_archive_primitives": ast_report.imported_archive_primitives,
                "novelty_classification": ast_report.novelty_classification,
                "novelty_notes": ast_report.novelty_notes,
                "stripped_operator_tuple": ast_report.stripped_operator_tuple,
            },
            "timestamp": time.time(),
        }

        legacy_out = island_dir / "legacy_out"
        legacy_out.mkdir(parents=True, exist_ok=True)
        (legacy_out / "metrics_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")

        # 记录入历史收据账本，支撑后续错题勘误追溯重算 (§7.3.2)
        with InterProcessFileLock(self.vault_dir / "eval_history.lock"):
            with self.receipts_history_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(receipt, ensure_ascii=False) + "\n")

        return receipt

    # ========================================================================
    # 3. 跨分支差分互测 (Cross-Branch Differential Testing, §7.4)
    # ========================================================================

    def run_differential_test(
        self,
        script_a_path: Path,
        script_b_path: Path,
        stress_inputs: Optional[List[Any]] = None,
        tolerance: float = 1e-5,
    ) -> Dict[str, Any]:
        """
        防自欺欺人交叉校验 (§7.4)：
        无需真值标签，用同一批极端边界测试算例同时喂给两条正交探索分支 A 与 B 的 `solve(x)`；
        一旦发现两条独立实现给出了显著冲突的输出，立即提取该分歧算例并返回，逼迫节点定位隐藏 Bug。
        """
        if not script_a_path.exists() or not script_b_path.exists():
            return {"status": "ERROR", "message": "差分互测脚本路径不存在"}

        test_cases = stress_inputs if stress_inputs is not None else [
            [],
            [0],
            [-100, 0, 100],
            [1, 1, 1, 1],
            [10, 25, -5, 42, 88, 13, 7, 99],
            [999999, -999999, 0, 42],
        ]

        driver_code = f"""
import importlib.util, json

def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

mod_a = load_mod("branch_a", r"{str(script_a_path.resolve())}")
mod_b = load_mod("branch_b", r"{str(script_b_path.resolve())}")
cases = {json.dumps(test_cases)}
results = []

for idx, inp in enumerate(cases):
    rec = {{"case_index": idx, "input": inp}}
    try:
        out_a = mod_a.solve(list(inp) if isinstance(inp, list) else inp)
        rec["out_a"] = out_a
    except Exception as e:
        rec["error_a"] = str(e)
    try:
        out_b = mod_b.solve(list(inp) if isinstance(inp, list) else inp)
        rec["out_b"] = out_b
    except Exception as e:
        rec["error_b"] = str(e)
    results.append(rec)

print("__GW_DIFF_JSON__:" + json.dumps(results))
"""
        sub_res = run_bounded_subprocess(
            cmd=[sys.executable, "-c", driver_code],
            cwd=script_a_path.parent,
            shared_readonly_dir=self.shared_readonly_dir,
            timeout_sec=30.0,
            max_memory_mb=2048,
        )
        if sub_res.exit_code != 0:
            return {
                "status": "ERROR",
                "message": f"差分互测进程异常退出: {(sub_res.stderr or sub_res.stdout)[-400:]}",
            }

        raw_list: List[Dict[str, Any]] = []
        for line in reversed(sub_res.stdout.splitlines()):
            if "__GW_DIFF_JSON__:" in line:
                raw_list = json.loads(line.split("__GW_DIFF_JSON__:", 1)[1].strip())
                break

        divergent_cases: List[Dict[str, Any]] = []
        for item in raw_list:
            if "error_a" in item or "error_b" in item:
                divergent_cases.append({**item, "reason": "ONE_OR_BOTH_CRASHED"})
                continue
            oa, ob = item.get("out_a"), item.get("out_b")
            if isinstance(oa, (int, float)) and isinstance(ob, (int, float)):
                if abs(float(oa) - float(ob)) > tolerance:
                    divergent_cases.append({**item, "diff": abs(float(oa) - float(ob)), "reason": "NUMERIC_DIVERGENCE"})
            elif oa != ob:
                divergent_cases.append({**item, "reason": "STRUCTURAL_DIVERGENCE"})

        return {
            "status": "OK",
            "total_cases_tested": len(raw_list),
            "consistent": len(divergent_cases) == 0,
            "divergent_cases": divergent_cases,
        }

    # ========================================================================
    # 4. 错题热勘误与历史分数追溯重算 (Retroactive Errata & Branch Revival, §7.3.2)
    # ========================================================================

    def get_deprecated_cases(self) -> Set[str]:
        if not self.errata_file.exists():
            return set()
        try:
            data = json.loads(self.errata_file.read_text(encoding="utf-8"))
            return set(data.get("deprecated_cases", {}).keys())
        except Exception:
            return set()

    def deprecate_errata_case(
        self,
        case_id: str,
        reason: str,
        anchor_s0_score: float = 0.0,
        higher_is_better: bool = True,
    ) -> Dict[str, Any]:
        """
        评测集错题热勘误与历史分数追溯重算 (§7.3.2)：
        1. 将存在生成器 Bug (如 NaN/Inf/违反物理守恒) 的测试算例 `case_id` 标记为 `ERRATA_DEPRECATED`；
        2. 自动扫描 `receipts_history.jsonl` 中所有带 `case_scores` 的历史候选解，剔除该错题后重新计算平均分；
        3. 若原先因该错题被判 `DEAD_END_ARCHIVE` 的候选解重算后超越 `anchor_s0_score`，立即将其加入 `revived_branches` 平反列表！
        """
        with InterProcessFileLock(self.vault_dir / "eval_history.lock"):
            errata_data = {"deprecated_cases": {}}
            if self.errata_file.exists():
                try:
                    errata_data = json.loads(self.errata_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            errata_data.setdefault("deprecated_cases", {})[case_id] = {
                "status": "ERRATA_DEPRECATED",
                "reason": reason,
                "deprecated_at": time.time(),
            }
            self.errata_file.write_text(json.dumps(errata_data, ensure_ascii=False, indent=2), encoding="utf-8")

            deprecated_set = set(errata_data["deprecated_cases"].keys())
            revived_branches: List[Dict[str, Any]] = []
            recomputed_receipts: List[Dict[str, Any]] = []

            if self.receipts_history_file.exists():
                lines = [ln.strip() for ln in self.receipts_history_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
                updated_lines: List[str] = []
                for ln in lines:
                    rec = json.loads(ln)
                    c_scores = rec.get("case_scores") or {}
                    if case_id in c_scores:
                        valid_vals = [float(v) for k, v in c_scores.items() if k not in deprecated_set]
                        if valid_vals:
                            old_frozen = float(rec["scores"]["frozen_benchmark"])
                            new_score = round(sum(valid_vals) / len(valid_vals), 6)
                            old_tier = rec.get("triage_tier", "DEAD_END_ARCHIVE")
                            new_tier = self._determine_triage_tier(
                                frozen_score=new_score,
                                niche_score=new_score,
                                anchor_s0_score=anchor_s0_score,
                                higher_is_better=higher_is_better,
                            )
                            rec["scores"]["frozen_benchmark"] = new_score
                            rec["scores"]["live_challenge"] = new_score
                            rec["triage_tier"] = new_tier
                            rec["hmac_sha256_signature"] = self.sign_receipt(
                                rec["node_id"], rec["commit_hash"], rec["run_nonce"], new_score, new_score
                            )
                            recomputed_receipts.append({
                                "node_id": rec["node_id"],
                                "commit_hash": rec["commit_hash"],
                                "old_score": old_frozen,
                                "new_score": new_score,
                                "old_tier": old_tier,
                                "new_tier": new_tier,
                            })
                            if old_tier == "DEAD_END_ARCHIVE" and new_tier in ("PARETO_PROMOTE", "NICHE_CHAMPION"):
                                revived_branches.append({
                                    "node_id": rec["node_id"],
                                    "commit_hash": rec["commit_hash"],
                                    "old_score": old_frozen,
                                    "new_score": new_score,
                                    "new_tier": new_tier,
                                })
                    updated_lines.append(json.dumps(rec, ensure_ascii=False))
                self.receipts_history_file.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

        return {
            "status": "OK",
            "deprecated_case_id": case_id,
            "recomputed_count": len(recomputed_receipts),
            "recomputed_receipts": recomputed_receipts,
            "revived_branches": revived_branches,
        }

    @staticmethod
    def _determine_triage_tier(
        frozen_score: float,
        niche_score: float,
        anchor_s0_score: float,
        higher_is_better: bool = True,
    ) -> str:
        if higher_is_better:
            if frozen_score > anchor_s0_score + 1e-6:
                return "PARETO_PROMOTE"
            if niche_score > anchor_s0_score * 1.05:
                return "NICHE_CHAMPION"
            return "DEAD_END_ARCHIVE"
        else:
            if anchor_s0_score > 0 and frozen_score < anchor_s0_score - 1e-6:
                return "PARETO_PROMOTE"
            if anchor_s0_score > 0 and niche_score < anchor_s0_score * 0.95:
                return "NICHE_CHAMPION"
            return "DEAD_END_ARCHIVE"

    @staticmethod
    def _build_builtin_eval_harness(script_abs_path: str, run_nonce: str, deprecated_cases: Optional[Set[str]] = None) -> str:
        """
        构建跨进程内置评测驱动脚本：
        - 若被测模块定义了 `evaluate()`，直接调用（支持返回含 `case_scores` 的字典）；
        - 若被测模块定义了 `solve(inputs)`，自动用标准算例与打乱顺序后的同构算例分别测试，检验是否背题号；
        - 输出带 `__GW_METRICS_JSON__:` 前缀的纯数据行。
        """
        dep_list = sorted(deprecated_cases or [])
        return f"""
import importlib.util, json, sys, random

spec = importlib.util.spec_from_file_location("cand_mod", r"{script_abs_path}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

deprecated = set({json.dumps(dep_list)})
metrics = {{"frozen_score": 0.0, "live_score": 0.0, "isomorphic_perturbation_gap": 0.0, "niche_hard_cases_score": 0.0, "case_scores": {{}}}}

if hasattr(mod, "evaluate") and callable(mod.evaluate):
    res = mod.evaluate()
    if isinstance(res, dict):
        for k, v in res.items():
            if isinstance(v, (int, float)):
                metrics[k] = float(v)
            elif k == "case_scores" and isinstance(v, dict):
                metrics["case_scores"] = {{str(ck): float(cv) for ck, cv in v.items() if isinstance(cv, (int, float))}}
        if metrics["case_scores"]:
            valid_vals = [val for cid, val in metrics["case_scores"].items() if cid not in deprecated]
            if valid_vals and "frozen_score" not in res:
                avg_s = sum(valid_vals) / len(valid_vals)
                metrics["frozen_score"] = avg_s
                metrics["live_score"] = avg_s
                metrics["niche_hard_cases_score"] = avg_s
    elif isinstance(res, (int, float)):
        metrics["frozen_score"] = float(res)
        metrics["live_score"] = float(res)
        metrics["niche_hard_cases_score"] = float(res)
elif hasattr(mod, "solve") and callable(mod.solve):
    base_inputs = [10, 25, -5, 42, 88, 13, 7, 99]
    out_normal = mod.solve(list(base_inputs))
    shuffled = list(base_inputs)
    random.Random(42).shuffle(shuffled)
    out_iso = mod.solve(shuffled)
    if isinstance(out_normal, (int, float)) and isinstance(out_iso, (int, float)):
        denom = max(1.0, abs(float(out_normal)))
        gap = abs(float(out_normal) - float(out_iso)) / denom
        score = float(out_normal)
        metrics["frozen_score"] = score
        metrics["live_score"] = score
        metrics["niche_hard_cases_score"] = score
        metrics["isomorphic_perturbation_gap"] = gap

print("__GW_METRICS_JSON__:" + json.dumps(metrics))
"""

    @staticmethod
    def _extract_metrics_from_stdout(stdout: str) -> Dict[str, Any]:
        for line in reversed(stdout.splitlines()):
            if "__GW_METRICS_JSON__:" in line:
                raw = line.split("__GW_METRICS_JSON__:", 1)[1].strip()
                try:
                    return json.loads(raw)
                except Exception:
                    pass
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    return json.loads(line)
                except Exception:
                    pass
        return {"frozen_score": 0.0, "live_score": 0.0, "isomorphic_perturbation_gap": 0.0, "niche_hard_cases_score": 0.0}
