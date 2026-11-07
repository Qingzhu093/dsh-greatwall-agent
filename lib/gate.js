/**
 * Cleanroom gate — the DeepSeek Harness port of `greatwall-agent/bin/hook_gate.py`.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * The Antigravity plugin enforces the clean-room boundary with a `PreToolUse`
 * hook: `hooks/hooks.json` pipes one JSON payload
 * (`{toolCall:{name,args:{Path,TargetFile,CommandLine}}}`) into
 * `bin/hook_gate.py`, which answers `{"decision":"deny","reason":...}`.
 * DSH has no stdin hook contract; its equivalent extension point is
 * `ctx.tools.guard(execution => string | undefined)` — a monotonic denial that
 * runs after pre-execute policy and approval. So the SAME three rules run here
 * as a guard callback.
 *
 * WHAT IS PORTED AND WHAT IS ADAPTED
 * ----------------------------------
 * Ported unchanged (policy): the four sensitive markers, the rule order, the
 * shell-write pattern list, the "one command may not reference two slots" check,
 * and every denial message — byte-identical to `hook_gate.py`.
 * Adapted (host skin only): how a tool call's candidate strings are read. DSH
 * tools are named `read` / `write` / `edit` / `pwsh` / `terminal_send` and carry
 * `file_path` / `command` / `text`, where Antigravity used `read_file` /
 * `write_file` / `run_command` and `Path` / `CommandLine`. `PATH_FIELDS` and
 * `COMMAND_FIELDS` below are the whole adapter; both spellings are accepted, so
 * the same object also serves callers that still pass Antigravity-shaped args.
 *
 * The original is deliberately zero-false-positive: a call that mentions none of
 * the four markers is allowed in ~0.1 ms and never inspected further. That
 * fast-path is preserved.
 *
 * @module dsh-greatwall-agent/gate
 */

/** Marker substrings that make a call part of a Great Wall campaign workspace. */
export const SENSITIVE_MARKERS = ['.kernel_vault', 'shared_readonly', 'worktrees/slot_', '../slot_']

/** Argument fields that can carry a path (DSH first, Antigravity aliases kept). */
export const PATH_FIELDS = [
  'file_path',
  'path',
  'target_path',
  'targetPath',
  'target_file',
  'targetFile',
  'target',
  'source_path',
  'destination_path',
  'cwd',
  'directory',
  'dir',
  'Path',
  'TargetFile',
]

/** Argument fields that can carry a shell command line. */
export const COMMAND_FIELDS = ['command', 'cmd', 'script', 'CommandLine', 'text']

/** Tool names that write file content directly. */
export const WRITE_TOOLS = new Set([
  'write',
  'edit',
  'multi_edit',
  'multiedit',
  'apply_patch',
  'write_file',
  'edit_file',
  'replace_file_content',
  'multi_replace_file_content',
])

/** Tool names that run a shell command line. */
export const COMMAND_TOOLS = new Set([
  'pwsh',
  'bash',
  'shell',
  'run_command',
  'execute_command',
  'terminal_send',
])

/** Shell-write patterns from `hook_gate.py`, in the original order. */
export const SHELL_WRITE_PATTERNS = [
  />/,
  /\bOut-File\b/i,
  /\bSet-Content\b/i,
  /\bAdd-Content\b/i,
  /\bRemove-Item\b/i,
  /\brm\s/i,
  /\bdel\s/i,
  /\bmv\s/i,
  /\bMove-Item\b/i,
]

/** Denial messages — byte-identical to `hook_gate.py`. */
export const DENY = {
  kernelVault:
    '🔒 [长城 Agent 清洁室隔离门禁] 严禁直接读取或修改 `.kernel_vault` 内核保险箱（含评测真值与 HMAC 密钥）！请使用 `gw_*` 标准 MCP 工具交互。',
  sharedReadonlyWrite:
    '🔒 [长城 Agent 只读档案馆门禁] `shared_readonly/` 为公共只读挂载区，严禁直接用写文件工具篡改！请在孤岛 `legacy_out/` 下提交遗产包并通过 `gw_submit_legacy` 验收入库。',
  sharedReadonlyShell:
    '🔒 [长城 Agent 只读档案馆门禁] 严禁通过终端命令重定向或修改 `shared_readonly/` 公共只读区！',
  crossSlot:
    '🔒 [长城 Agent 跨孤岛防偷看门禁] 严禁通过 `../slot_*` 越界访问其他并行探索槽位的私有目录！',
}

/** Cross-slot denial, mirroring the f-string in `hook_gate.py`. */
export function crossSlotMultiMessage(slots) {
  return `🔒 [长城 Agent 跨孤岛防偷看门禁] 检测到单次操作同时引用多个孤岛槽位 ${JSON.stringify(
    [...slots].sort(),
  )}，严禁跨槽位偷看或拷贝未验收入库的半成品代码！`
}

/**
 * Read the string values of `fields` from a tool-call argument object.
 * @param {unknown} args - parsed tool arguments (an object is expected; a JSON string is tolerated).
 * @param {readonly string[]} fields - candidate field names.
 * @returns {string} space-joined values.
 */
export function pickFields(args, fields) {
  let source = args
  if (typeof source === 'string') {
    try {
      source = JSON.parse(source)
    } catch {
      return source
    }
  }
  if (source === null || typeof source !== 'object') return ''
  const values = []
  for (const field of fields) {
    const value = source[field]
    if (typeof value === 'string') values.push(value)
  }
  return values.join(' ')
}

/** Backslashes to slashes, exactly as the Python hook does before matching. */
export function normalizeText(text) {
  return String(text ?? '').replace(/\\/g, '/')
}

/**
 * The three clean-room rules, ported one-to-one from `evaluate_hook()`.
 * @param {string} toolName - model-facing tool name.
 * @param {unknown} args - tool arguments.
 * @returns {string | undefined} denial reason, or `undefined` to allow.
 */
export function evaluateGate(toolName, args) {
  const name = String(toolName ?? '').toLowerCase()
  const pathText = normalizeText(pickFields(args, PATH_FIELDS))
  const commandText = normalizeText(pickFields(args, COMMAND_FIELDS))
  const combined = `${pathText} ${commandText}`

  // Fast path: this call never touches a campaign workspace.
  if (!SENSITIVE_MARKERS.some((marker) => combined.includes(marker))) return undefined

  // 1. The kernel vault is closed to file and shell tools alike.
  if (combined.includes('.kernel_vault')) return DENY.kernelVault

  // 2. `shared_readonly/` is a read-only mount: no file writes, no shell writes.
  if (combined.includes('shared_readonly')) {
    if (WRITE_TOOLS.has(name)) return DENY.sharedReadonlyWrite
    if (COMMAND_TOOLS.has(name) && SHELL_WRITE_PATTERNS.some((pattern) => pattern.test(commandText))) {
      return DENY.sharedReadonlyShell
    }
  }

  // 3. No peeking across parallel clean-room slots.
  if (combined.includes('../slot_')) return DENY.crossSlot
  const referenced = new Set(
    Array.from(combined.matchAll(/worktrees\/(slot_[a-zA-Z0-9_-]+)/g), (match) => match[1]),
  )
  if (referenced.size > 1) return crossSlotMultiMessage(referenced)

  return undefined
}
