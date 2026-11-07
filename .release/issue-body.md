<!--
  Ready-to-paste body for the Open Plugin Market submission.

  gh issue create --repo polang233/dsh-plugin-index `
    --title "[plugin-add] dsh-greatwall-agent" `
    --body-file .release/issue-body.md

  Written to match this template:
  https://github.com/polang233/dsh-plugin-index/blob/main/.github/ISSUE_TEMPLATE/plugin-add.yml
  Fill in the optional screenshots section only after hiding keys and personal data.
-->

### 插件地址 / Plugin link

- npm package: `dsh-greatwall-agent` — https://www.npmjs.com/package/dsh-greatwall-agent
- Source repository: https://github.com/Qingzhu093/dsh-greatwall-agent
- The plugin is at the repository root (no subdirectory).

### 简短说明 / Summary

**中文**：长城 Agent V4.2 —— 面向长程无人值守科研攻关与算法竞赛的 DSH 插件：内置 Phase 0 开局先蒸馏、无 `.git` 清洁室孤岛沙箱、MLE-STAR 局部代码块微创替换、HMAC 防伪隔离评测、零向量 L0/L1/L2 档案馆与终局防吹牛五件套交付。

**English**：Great Wall Agent V4.2 — a DSH plugin for unattended long-horizon AI-for-Science and algorithm-competition campaigns: opening distillation, git-free clean-room slots, MLE-STAR surgical code replacement, HMAC-sealed isolated evaluation, a zero-vector L0/L1/L2 archive, and anti-bluff final delivery.

### 插件实际效果 / Plugin screenshots

Not attached yet — the UI surface is a tool set plus a registered skill rather than a new page.
I can add real campaign screenshots (no keys, no personal data) on request.

### 补充信息 / Additional details

- **Logo**: <https://raw.githubusercontent.com/Qingzhu093/dsh-greatwall-agent/main/icon.svg>
- **Tested**: DSH `0.2.2-rc.1` · Windows 11 · Python 3.14 (the plugin speaks MCP over stdio to a local Python server).
- **Verified in a live session**: the nine `gw_*` tools are mounted as `mcp__greatwall-agent__gw_*` (`gw_init_campaign` … `gw_compile_delivery`), the `greatwall-campaign` skill registers from the installed package, and the clean-room gate is installed as a tool guard.
- **Compatibility**: `engines.dsh: ">=0.2.2-rc.1 <0.3.0-0"` (also declared for `@deepseek-ai/dsh-mcp-client`).
- **Bundle**: `dsh.bundle.patch: ./cordis.patch.yml`, and `cordis.patch.yml` is inside the published tarball.
- **License**: MIT, with a `LICENSE` file in the repository and a `license` field in `package.json`.
- **npm tag**: `latest` → `4.2.0`.
- **Provenance**: `greatwall-agent/` (the Python kernel, skills, agents, hooks) is shipped byte-identical to the original Antigravity plugin; `core-manifest.sha256` plus `node tools/verify-core.mjs` let anyone re-hash all 18 files.
- **Security self-check against the common rejection reasons** (from `CONTRIBUTING.md`): the package registers no `webServer` route, so it adds no CORS surface and no route-authentication gap; it makes no outbound HTTP requests and stores no credentials. It starts a local Python MCP server over stdio, and its tools work inside the campaign workspace — the clean-room gate denies out-of-slot writes.
