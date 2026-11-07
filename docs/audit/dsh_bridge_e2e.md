# DSH MCP 桥端到端实测（2026-11-07）

在 **DSH 运行中的 MCP 客户端**（`mcp__greatwall-agent__*`）上实际调用本插件暴露的工具，
用于验证“9 工具 → MCP 桥 → DSH Agent”这条真实链路（而非仅自建 stdio 探针）。

## 1. `gw_init_campaign`

请求（DSH 工具调用参数）：

```json
{
  "workspaceRoot": "C:\\Users\\wangy\\AppData\\Local\\Temp\\gw-dsh-bridge-audit\\ws",
  "taskId": "DSH_BRIDGE_E2E_AUDIT",
  "taskDescription": "DSH MCP bridge end-to-end verification for the audit report (temporary workspace)",
  "domainType": "ALGO_COMPETITION",
  "primaryMetric": "score",
  "higherIsBetter": true
}
```

DSH 返回（已由 DSH 桥把 `content[0].text` 反序列化为对象）：

```json
{
  "status": "OK",
  "workspace_root": "C:\\Users\\wangy\\AppData\\Local\\Temp\\gw-dsh-bridge-audit\\ws",
  "task_config_path": "C:\\Users\\wangy\\AppData\\Local\\Temp\\gw-dsh-bridge-audit\\ws\\shared_readonly\\task_config.yaml",
  "discovered_data_modalities": [],
  "eda_probe_report": {"probed_at": "2026-11-07T13:22:21Z", "total_files": 0, "modalities": []},
  "next_step": "请运行 Phase 0 开局知识蒸馏，然后调用 gw_lock_distillation 固化 SOTA 锚点卡与零号强基线 s_0。"
}
```

## 2. `gw_archive_query` (`get_campaign_status`)

请求：

```json
{"workspaceRoot": "C:\\Users\\wangy\\AppData\\Local\\Temp\\gw-dsh-bridge-audit\\ws", "action": "get_campaign_status"}
```

DSH 返回（节选）：

```json
{
  "status": "OK",
  "campaign_state": {
    "initialized": true,
    "task_id": "DSH_BRIDGE_E2E_AUDIT",
    "domain_type": "ALGO_COMPETITION",
    "primary_metric": "score",
    "higher_is_better": true,
    "anchor_s0_commit": "",
    "anchor_s0_score": 0.0,
    "total_steps_executed": 0,
    "total_step_budget": 240,
    "max_concurrent_slots": 4,
    "active_slots": {},
    "lineages": {},
    "pending_proposals": [],
    "reflections_completed": 0,
    "data_inventory": [],
    "created_at": 1794057741.460514
  },
  "campaign_stage": {
    "stage": "STAGE_0_DISTILLATION",
    "budget_progress": 0.0,
    "steps_executed": 0,
    "total_step_budget": 240,
    "stage_policy": "完成开局静态数据探针 (EDA) 与多候选零号基线 s_0 实跑锁定。"
  }
}
```

## 3. 结论

- DSH 桥能正常发现并调用 9 个工具（`tools/list` 元数据与参数 schema 被 DSH 接受），**桥本身可用**。
- 工作区全部使用 `%TEMP%`，未在仓库内创建运行数据（本次审计中唯一一次仓库内工作区污染来自
  `probe_mcp_conformance.py` 的畸形帧用例，已记录为缺陷 P2-1 并清理，见 `accidental_workspace_evidence.json`）。
- 桥可用不代表协议/语义合规：见 `../BUG_REPORT.md` 的 P0-1（非对象 JSON 帧崩服务）与
  P0-2（业务错误一律 `isError=false`），这两个缺陷在 DSH 桥层同样会暴露。
