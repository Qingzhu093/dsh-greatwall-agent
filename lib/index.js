/**
 * dsh-greatwall-agent — DeepSeek Harness host entry for the Great Wall Agent V4.2 port.
 *
 * WHAT THIS PLUGIN DELIVERS
 * -------------------------
 * The Antigravity plugin shipped three host-facing things beside its Python core:
 * an MCP server registration (`mcp_config.json`), a skill (`skills/greatwall-campaign`),
 * and a `PreToolUse` clean-room gate (`hooks/hooks.json` + `bin/hook_gate.py`).
 * DSH has a different host contract, so `apply` maps each one onto the native DSH
 * extension point — the Python core itself is shipped byte-identical under
 * `greatwall-agent/` and is not modified in any way:
 *
 *   Antigravity                        | DeepSeek Harness (this file)
 *   -----------------------------------|---------------------------------------------
 *   `mcp_config.json`                  | `@deepseek-ai/dsh-mcp-client` mounted here
 *   `skills/greatwall-campaign`        | `ctx.skills.register()` (lib/skillpack.js)
 *   `hooks/hooks.json` + hook_gate.py  | `ctx.tools.guard()` (lib/gate.js)
 *
 * The MCP server is mounted from JavaScript rather than declared in
 * `cordis.patch.yml` for one reason: the patch row would need an absolute path to
 * `greatwall-agent/bin/gw_mcp_server.py`, while a JS mount resolves it from
 * `import.meta.url`. The same package therefore works from a profile install, a
 * pnpm store, a linked checkout, or `node_modules`, on every platform.
 *
 * LOADING CONTRACT
 * ----------------
 * Static imports plus a synchronous `apply()` keep registration ordering obvious.
 * Each delivered capability is guarded independently, so one broken subsystem
 * degrades to "not registered" instead of failing the whole plugin — the same
 * policy the reference DSH plugins use.
 *
 * @module dsh-greatwall-agent
 */
import { fileURLToPath } from 'node:url'
import Schema from '@deepseek-ai/schemastery'
import * as McpClient from '@deepseek-ai/dsh-mcp-client'
import { evaluateGate } from './gate.js'
import { loadSkillPack, registerSkillPack } from './skillpack.js'

/** Package name (also the bundle row name in `package.json`). */
export const name = 'dsh-greatwall-agent'

/** This plugin needs the tool registry to install its clean-room guard. */
export const inject = ['tools']

/**
 * MCP namespace. The original Antigravity `mcp_config.json` registered the server
 * under the key `greatwall-agent`, so the same name is kept here: the model sees
 * `mcp__greatwall-agent__gw_init_campaign` and its eight siblings. The namespace
 * must match `^[A-Za-z0-9_-]{1,32}$` — `greatwall-agent` does.
 */
export const SERVER_NAME = 'greatwall-agent'

/** `python` on Windows, `python3` elsewhere — overridable through `pythonPath`. */
export const DEFAULT_PYTHON = process.platform === 'win32' ? 'python' : 'python3'

/**
 * Cordis config schema (validated before `apply`; omitted fields take these
 * defaults, so `cordis.patch.yml` deliberately carries no `config:` block).
 */
export const Config = Schema.object({
  pythonPath: Schema.string().default(DEFAULT_PYTHON),
  cleanroomGate: Schema.boolean().default(true),
})

/** The shipped, byte-identical Antigravity plugin tree. */
const CORE_ROOT = fileURLToPath(new URL('../greatwall-agent/', import.meta.url))
/** The unchanged Python stdio MCP server. */
const SERVER_SCRIPT = fileURLToPath(new URL('../greatwall-agent/bin/gw_mcp_server.py', import.meta.url))
/** The unchanged `greatwall-campaign` skill directory. */
const SKILLS_DIR = fileURLToPath(new URL('../greatwall-agent/skills/', import.meta.url))

/**
 * Prepended to the registered skill body. The skill text is the original
 * `SKILL.md` verbatim; this note only tells the model what the MCP bridge names
 * the very tools the text refers to by their bare `gw_*` names.
 */
const HOST_MAPPING_NOTE = [
  '> **DeepSeek Harness 宿主适配说明（工具名映射）**：本技能由 `dsh-greatwall-agent` 插件交付，通过 DSH 官方 MCP 桥（`@deepseek-ai/dsh-mcp-client`）暴露与原 Antigravity 版本完全相同的内核工具。',
  `> 模型侧公开名为 \`mcp__${SERVER_NAME}__<原始名>\`，例如 \`mcp__${SERVER_NAME}__gw_init_campaign\`。`,
  '> 下文出现的裸名 `gw_xxx` 均指对应的 MCP 工具；参数、返回与裁决逻辑与原插件一致。',
  '',
  '',
].join('\n')

/**
 * Read the logger if this harness exposes one. Never required: a deployment
 * without a logger must still get the tools and the gate.
 * @param {any} ctx - plugin context.
 * @returns {{info: Function, warn: Function}} safe logger facade.
 */
function safeLogger(ctx) {
  const logger = ctx?.logger ?? ctx?.root?.logger
  return {
    info: (message) => {
      try {
        logger?.info?.(message)
      } catch {
        /* logging must never break activation */
      }
    },
    warn: (message) => {
      try {
        logger?.warn?.(message)
      } catch {
        /* logging must never break activation */
      }
    },
  }
}

/**
 * Mount the official MCP client on this plugin's context so it owns the stdio
 * child process for as long as this plugin is loaded.
 * @param {any} ctx - plugin context.
 * @param {string} pythonPath - interpreter used to run the server.
 * @returns {{mounted: boolean, error?: string}} mount outcome.
 */
function mountMcpServer(ctx, pythonPath) {
  try {
    ctx.plugin(McpClient, {
      transport: 'stdio',
      serverName: SERVER_NAME,
      command: pythonPath,
      args: [SERVER_SCRIPT],
      env: {
        PYTHONUTF8: '1',
        PYTHONIOENCODING: 'utf-8',
        PYTHONUNBUFFERED: '1',
        // Never write __pycache__ back into the installed package. A `files`
        // whitelist wins over .gitignore, so a cache created here would end up in
        // the published tarball; tools/clean-pycache.mjs also runs on prepack.
        PYTHONDONTWRITEBYTECODE: '1',
      },
      // `gw_evaluate_slot` runs a real isolated evaluation; 10 minutes beats the
      // 60 s default without hiding a hung call forever.
      toolCallTimeoutMs: 600000,
      // A missing Python must not take the whole DSH profile down.
      failOnStartupError: false,
      reconnect: { enabled: true, initialDelayMs: 500, maxDelayMs: 30000, maxAttempts: 10 },
    })
    return { mounted: true }
  } catch (error) {
    return { mounted: false, error: String(error?.message ?? error) }
  }
}

/**
 * Register the `greatwall-campaign` skill.
 * @param {any} ctx - plugin context.
 * @param {object} logger - safe logger.
 * @returns {{delivered: boolean, registered: string[], failed: Array<object>, problems: Array<object>}}
 */
function deliverSkillPack(ctx, logger) {
  const result = { delivered: false, registered: [], failed: [], problems: [] }
  let service
  try {
    service = typeof ctx.get === 'function' ? ctx.get('skills') : undefined
  } catch {
    service = undefined
  }
  if (!service || typeof service.register !== 'function') return result
  result.delivered = true
  try {
    const pack = loadSkillPack(SKILLS_DIR)
    result.problems = pack.problems
    const skills = pack.skills.map((skill) => ({
      ...skill,
      content: skill.name === 'greatwall-campaign' ? HOST_MAPPING_NOTE + skill.content : skill.content,
    }))
    const outcome = registerSkillPack(service, skills, { provider: 'dsh-greatwall-agent' })
    result.registered = outcome.registered
    result.failed = outcome.failed
  } catch (error) {
    result.failed.push({ name: '*', message: String(error?.message ?? error) })
  }
  if (result.failed.length > 0) {
    logger.warn('[dsh-greatwall-agent] skill registration failed: ' + result.failed.map((f) => `${f.name}: ${f.message}`).join('; '))
  }
  if (result.problems.length > 0) {
    logger.warn('[dsh-greatwall-agent] skill pack problems: ' + result.problems.map((p) => `${p.dir}: ${p.reason}`).join('; '))
  }
  return result
}

/**
 * Install the clean-room gate as a DSH tool guard.
 * @param {any} ctx - plugin context.
 * @param {boolean} enabled - config switch (`cleanroomGate`).
 * @returns {boolean} whether the guard is installed.
 */
function installCleanroomGate(ctx, enabled) {
  if (!enabled) return false
  const registry = ctx.tools
  if (!registry || typeof registry.guard !== 'function') return false
  ctx.effect(
    () => registry.guard((execution) => evaluateGate(execution?.name, execution?.arguments)),
    'dsh-greatwall-agent.cleanroomGate',
  )
  return true
}

/**
 * Cordis entry: deliver the MCP bridge, the skill and the clean-room gate.
 * @param {any} ctx - plugin context (with `tools` injected).
 * @param {{pythonPath?: string, cleanroomGate?: boolean}} config - resolved config.
 * @returns {{mcp: object, skills: object, gate: boolean}} delivery report.
 */
export function apply(ctx, config) {
  const logger = safeLogger(ctx)
  const pythonPath =
    typeof config?.pythonPath === 'string' && config.pythonPath.trim().length > 0
      ? config.pythonPath.trim()
      : DEFAULT_PYTHON

  const mcp = mountMcpServer(ctx, pythonPath)
  if (!mcp.mounted) logger.warn('[dsh-greatwall-agent] MCP mount failed: ' + mcp.error)

  const skills = deliverSkillPack(ctx, logger)
  const gate = installCleanroomGate(ctx, config?.cleanroomGate !== false)

  logger.info(
    `[dsh-greatwall-agent] core=${CORE_ROOT} python=${pythonPath} mcp=${mcp.mounted ? SERVER_NAME : 'failed'} ` +
      `skills=${skills.registered.length > 0 ? skills.registered.join(',') : 'none'} gate=${gate ? 'on' : 'off'}`,
  )

  return { mcp, skills, gate }
}
