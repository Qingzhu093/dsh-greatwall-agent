/**
 * Skill pack — deliver this package's `skills/` directory through `ctx.skills`.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * A DSH skill provider only discovers skills from *configured roots*
 * (`<project>/.dsh/skills`, `<dshHome>/skills`, `Config.customSkillDirs`,
 * `Config.bundledSkillDir`). An npm package's own `skills/` directory is not one
 * of them, so an npm-delivered plugin must register its skills itself:
 * `ctx.skills.register(skill)` during `apply()`. Registration is an effect, so it
 * is undone automatically on unload — no installer, no symlink, no profile edit.
 *
 * This module only reads and parses. It imports no DSH package, which keeps it
 * unit-testable with a plain `node --test` stub.
 *
 * @module dsh-greatwall-agent/skillpack
 */
import fs from 'node:fs'
import path from 'node:path'

/** Official rule from the DSH skills reference: kebab-case. */
export const SKILL_NAME_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

/**
 * Parse the minimal YAML frontmatter a skill needs (`name`, `description`,
 * optional `whenToUse` / `when_to_use`). Deliberately not a YAML parser: the
 * contract only requires plain scalars, and this package stays dependency-free.
 * @param {string} text - `SKILL.md` content.
 * @returns {{ok: true, name: string, description: string, whenToUse: string|null, body: string} | {ok: false, reason: string}}
 */
export function parseSkillDocument(text) {
  const source = String(text ?? '')
  if (!source.startsWith('---')) return { ok: false, reason: 'NO_FRONTMATTER' }
  const end = source.indexOf('\n---', 3)
  if (end < 0) return { ok: false, reason: 'UNTERMINATED_FRONTMATTER' }
  const block = source.slice(3, end)
  const read = (key) => {
    const match = new RegExp('^' + key + ':\\s*(.*)$', 'm').exec(block)
    if (!match) return null
    const value = match[1].trim()
    if (value.startsWith('|') || value.startsWith('>')) return null
    return value.replace(/^['"]|['"]$/g, '')
  }
  const name = read('name')
  const description = read('description')
  if (!name) return { ok: false, reason: 'MISSING_NAME' }
  if (!description) return { ok: false, reason: 'MISSING_DESCRIPTION' }
  const body = source.slice(source.indexOf('\n', end + 1) + 1).replace(/^\s*\n/, '')
  return { ok: true, name, description, whenToUse: read('whenToUse') ?? read('when_to_use'), body }
}

/**
 * Load every `<name>/SKILL.md` under a directory. Invalid entries are reported
 * in `problems` instead of being dropped silently.
 * @param {string} skillsDir - directory holding one subdirectory per skill.
 * @returns {{skills: Array<{name: string, description: string, whenToUse: string|null, content: string, dir: string}>, problems: Array<{dir: string, reason: string}>}}
 */
export function loadSkillPack(skillsDir) {
  const skills = []
  const problems = []
  let entries
  try {
    entries = fs.readdirSync(skillsDir, { withFileTypes: true })
  } catch (error) {
    return { skills, problems: [{ dir: skillsDir, reason: 'SKILLS_DIR_UNREADABLE: ' + String(error?.message ?? error) }] }
  }
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    if (!entry.isDirectory()) continue
    const file = path.join(skillsDir, entry.name, 'SKILL.md')
    if (!fs.existsSync(file)) {
      problems.push({ dir: entry.name, reason: 'NO_SKILL_MD' })
      continue
    }
    let parsed
    try {
      parsed = parseSkillDocument(fs.readFileSync(file, 'utf8'))
    } catch (error) {
      problems.push({ dir: entry.name, reason: 'READ_FAILED: ' + String(error?.message ?? error) })
      continue
    }
    if (!parsed.ok) {
      problems.push({ dir: entry.name, reason: parsed.reason })
      continue
    }
    if (!SKILL_NAME_RE.test(parsed.name)) {
      problems.push({ dir: entry.name, reason: 'INVALID_NAME: ' + parsed.name })
      continue
    }
    if (parsed.name !== entry.name) {
      problems.push({ dir: entry.name, reason: 'NAME_DIRECTORY_MISMATCH: frontmatter="' + parsed.name + '" dir="' + entry.name + '"' })
      continue
    }
    if (parsed.body.trim().length === 0) {
      problems.push({ dir: entry.name, reason: 'EMPTY_BODY' })
      continue
    }
    skills.push({
      name: parsed.name,
      description: parsed.description,
      whenToUse: parsed.whenToUse,
      content: parsed.body,
      dir: entry.name,
    })
  }
  return { skills, problems }
}

/**
 * Register a loaded pack on a `skills` service.
 * @param {{register: Function}} service - `ctx.skills`.
 * @param {Array<object>} skills - output of {@link loadSkillPack}.
 * @param {{modelInvocable?: boolean, userInvocable?: boolean, provider?: string}} [options] - invocation policy.
 * @returns {{registered: string[], failed: Array<{name: string, message: string}>}}
 */
export function registerSkillPack(service, skills, options = {}) {
  const registered = []
  const failed = []
  const invocation = {
    modelInvocable: options.modelInvocable !== false,
    userInvocable: options.userInvocable !== false,
  }
  for (const skill of skills) {
    try {
      service.register({
        name: skill.name,
        description: skill.description,
        ...(skill.whenToUse ? { whenToUse: skill.whenToUse } : {}),
        content: skill.content,
        invocation,
        ...(options.provider ? { provider: options.provider } : {}),
      })
      registered.push(skill.name)
    } catch (error) {
      failed.push({ name: skill.name, message: String(error?.message ?? error) })
    }
  }
  return { registered, failed }
}
