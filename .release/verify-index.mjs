#!/usr/bin/env node
/**
 * verify-index.mjs — offline validator for a DSH plugin-market index (`format: 1`).
 *
 * Rule sources (both read while building this file, no guessing):
 *   1. The executable rule set pinned to the RUNNING DSH release (0.2.2-rc.1):
 *      https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-rc.1/.agents/notes/implemented/feature/2026-10-02-plugin-market-index-format.md
 *   2. The published guide:
 *      https://deepseek-harness.github.io/deepseek-harness/en/guide/plugin-market.md
 *
 * Where the two disagree the pinned tag wins (see README of this directory):
 *   - the guide calls `engines.dsh` optional; the pinned note makes `engines` and
 *     `engines.dsh` REQUIRED on every version. This validator requires them.
 *   - the pinned note adds rules the guide omits: `LocalizedText` keys are
 *     lowercase language ids and every string needs a non-space character;
 *     `publishTimestamp` is an integer in [0, 10^11); an npm `version` must be a
 *     canonical published version (`semver.valid(v) === v`).
 *
 * The one deliberate deviation: this repo keeps the market index under version
 * control BEFORE the npm publish exists, so `publishTimestamp` carries the token
 * `"__PUBLISH_TIMESTAMP__"`. That token is accepted (and reported as a warning)
 * so the committed file can be validated; `--strict` — the mode used for the
 * publish build — rejects it.
 *
 * Usage:
 *   node .release/verify-index.mjs [indexPath] [options]
 *
 * Options:
 *   --base-url <url>     URL the index will be served from, used to resolve
 *                        relative icon references (default: GitHub Pages URL).
 *   --dsh-version <v>    DSH version to test `engines.dsh` against (default 0.2.2-rc.1).
 *   --strict             Reject the __PUBLISH_TIMESTAMP__ placeholder.
 *   --no-package-check   Skip the cross-check against ../package.json.
 *   --no-icon-files      Skip the on-disk existence check for relative icons.
 *   -h, --help           Show this help.
 *
 * Exit codes: 0 = pass (warnings allowed), 1 = validation errors, 2 = usage/IO error.
 */

import { existsSync, readFileSync, statSync } from 'node:fs'
import { builtinModules, createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const PLACEHOLDER = '__PUBLISH_TIMESTAMP__'
const MAX_INDEX_BYTES = 128 * 1024 * 1024
const DEFAULT_BASE_URL = 'https://qingzhu093.github.io/dsh-greatwall-agent/market/index.json'
const DEFAULT_DSH_VERSION = '0.2.2-rc.1'
const DEFAULT_INDEX = fileURLToPath(new URL('../market/index.json', import.meta.url))
const DEFAULT_PACKAGE_JSON = fileURLToPath(new URL('../package.json', import.meta.url))

/** SemVer 2.0.0 — the same grammar node-semver accepts (no `v` prefix, no leading zeros). */
const SEMVER_RE =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$/

/** npm's validator for NEW package names: lowercase, URL-safe, one optional @scope. */
const NPM_NAME_RE = /^(?:@[a-z0-9-~][a-z0-9-._~]*\/)?[a-z0-9-~][a-z0-9-._~]*$/
const NPM_NAME_BLACKLIST = new Set(['node_modules', 'favicon.ico'])
const LANGUAGE_ID_RE = /^[a-z]{2,8}(-[a-z0-9]{1,8})*$/
/** Git-source / repository.directory path segments. */
const PATH_SEGMENT_RE = /^[A-Za-z0-9._@+-]+$/
const DATA_ICON_RE = /^data:(image\/(?:svg\+xml|png|jpeg|webp));base64,([A-Za-z0-9+/]+={0,2})$/

const errors = []
const warnings = []
const notes = []
const err = (at, msg) => errors.push(`${at}: ${msg}`)
const warn = (at, msg) => warnings.push(`${at}: ${msg}`)

// ---------------------------------------------------------------------------
// semver: use the copy npm ships when we can find it, else fall back to the
// grammar checks below (the fallback only weakens range checking, and says so).
// ---------------------------------------------------------------------------

function loadSemver() {
  const require = createRequire(import.meta.url)
  const execDir = path.dirname(process.execPath)
  const candidates = [
    process.env.DSH_VERIFY_SEMVER_PATH,
    path.join(execDir, 'node_modules', 'npm', 'node_modules', 'semver'), // Windows npm install
    path.join(execDir, '..', 'lib', 'node_modules', 'npm', 'node_modules', 'semver'), // POSIX npm install
    'semver',
  ].filter(Boolean)
  for (const candidate of candidates) {
    try {
      return require(candidate)
    } catch {
      /* try next */
    }
  }
  return null
}

const semver = loadSemver()

/** Fallback range grammar, used only when node-semver is unavailable. */
function looksLikeRange(range) {
  const alternatives = range.split('||')
  if (alternatives.some((alt) => alt.trim() === '')) return false
  const version = '(?:0|[1-9]\\d*)\\.(?:0|[1-9]\\d*)\\.(?:0|[1-9]\\d*)' + '(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?'
  const partial = '(?:0|[1-9]\\d*|[xX*])(?:\\.(?:0|[1-9]\\d*|[xX*])){0,2}'
  const hyphen = new RegExp(`^\\s*${version}\\s+-\\s+${version}\\s*$`)
  const comparator = new RegExp(`^(?:(?:<=|>=|<|>|=|\\^|~)\\s*)?(?:${version}|${partial}|[xX*])$`)
  for (const alternative of alternatives) {
    const part = alternative.trim()
    if (hyphen.test(part)) continue
    const tokens = part.split(/\s+/)
    if (tokens.length === 0 || tokens.some((token) => !comparator.test(token))) return false
  }
  return true
}

function isValidVersion(value) {
  if (typeof value !== 'string' || !SEMVER_RE.test(value)) return false
  if (!semver) return true
  // node-semver rejects numeric prerelease identifiers with leading zeros, which
  // the plain grammar above already forbids; keep the canonical check.
  return semver.valid(value) === value
}

function isValidRange(value) {
  if (typeof value !== 'string' || value.trim() === '') return false
  if (semver) return semver.validRange(value) !== null
  return looksLikeRange(value.trim())
}

// ---------------------------------------------------------------------------
// small helpers
// ---------------------------------------------------------------------------

const isObject = (value) => typeof value === 'object' && value !== null && !Array.isArray(value)
const isNonBlank = (value) => typeof value === 'string' && value.trim().length > 0
const show = (value) => (typeof value === 'string' ? JSON.stringify(value) : String(value))

/** Copy the spec's JSON path convention: `plugins[0].versions[0].version`. */
function at(base, ...segments) {
  return segments.reduce(
    (acc, segment) => (typeof segment === 'number' ? `${acc}[${segment}]` : `${acc}.${segment}`),
    base,
  )
}

function checkLocalizedText(value, where, { required = false } = {}) {
  if (value === undefined) {
    if (required) err(where, 'required LocalizedText is missing')
    return
  }
  if (typeof value === 'string') {
    if (!value.trim()) err(where, 'a LocalizedText string must contain at least one non-whitespace character')
    return
  }
  if (!isObject(value)) {
    err(where, `LocalizedText must be a string or an object of language id → string, got ${show(value)}`)
    return
  }
  const languages = Object.keys(value)
  if (!languages.includes('en')) err(where, 'a LocalizedText object must contain "en"')
  for (const language of languages) {
    if (!LANGUAGE_ID_RE.test(language)) {
      err(at(where, language), `"${language}" is not a lowercase language id (expected ${LANGUAGE_ID_RE})`)
    }
    const text = value[language]
    if (typeof text !== 'string') err(at(where, language), `must be a string, got ${show(text)}`)
    else if (!text.trim()) err(at(where, language), 'must contain at least one non-whitespace character')
  }
}

/**
 * URL check. The format note forbids credentials/query/fragment on `repository.url`
 * and `source.registry` and on a git `source.url`; `homepage` only has to be an
 * absolute http(s) page URL, so it may carry a `#readme` fragment.
 */
function checkHttpUrl(value, where, { requireHttps = false, label = 'URL', allowQuery = false, allowHash = false, allowCredentials = false } = {}) {
  if (typeof value !== 'string') {
    err(where, `must be a string, got ${show(value)}`)
    return null
  }
  let url
  try {
    url = new URL(value)
  } catch {
    err(where, `is not an absolute ${label}: ${show(value)}`)
    return null
  }
  const allowed = requireHttps ? ['https:'] : ['http:', 'https:']
  if (!allowed.includes(url.protocol)) {
    err(where, `must use ${allowed.join(' or ')}, got ${show(url.protocol)}`)
    return null
  }
  if (!allowCredentials && (url.username || url.password)) err(where, 'must not contain credentials')
  if (!allowQuery && url.search) err(where, 'must not contain a query string')
  if (!allowHash && url.hash) err(where, 'must not contain a fragment')
  return url
}

/** The `path` rule shared by git sources and `repository.directory`. */
function checkRelativeDirectory(value, where) {
  if (value === undefined) return
  if (typeof value !== 'string' || value.length === 0) {
    err(where, 'must be a non-empty "/"-separated relative directory')
    return
  }
  if (value.startsWith('/') || /^[A-Za-z]:/.test(value) || value.includes('\\')) {
    err(where, `must be a relative "/"-separated path, got ${show(value)}`)
    return
  }
  const segments = value.split('/')
  if (segments.some((segment) => segment.length === 0)) err(where, `must not contain an empty path segment: ${show(value)}`)
  for (const segment of segments) {
    if (segment === '.' || segment === '..') err(where, `must not contain "." or ".." segments: ${show(value)}`)
    else if (!PATH_SEGMENT_RE.test(segment)) err(where, `segment ${show(segment)} may only contain ASCII letters, digits and . _ @ + -`)
  }
}

function validatePackageName(name, where) {
  if (typeof name !== 'string') {
    err(where, `must be a string, got ${show(name)}`)
    return
  }
  if (name.length === 0 || name.length > 214) err(where, 'must be 1–214 characters long')
  if (NPM_NAME_BLACKLIST.has(name)) err(where, `"${name}" is reserved by npm`)
  else if (!NPM_NAME_RE.test(name)) err(where, `is not a valid npm package name for a new package: ${show(name)}`)
  else if (nodeIsBuiltin(name)) warn(where, `"${name}" collides with a Node.js core module name`)
}

function nodeIsBuiltin(name) {
  return builtinModules.includes(name)
}

// ---------------------------------------------------------------------------
// icon resolution
// ---------------------------------------------------------------------------

/**
 * @returns {{kind: 'none'|'inline'|'url', resolved?: string}|null} null when invalid.
 */
function checkIcon(value, where, baseUrl, { checkFiles, indexDir }) {
  if (value === undefined) return { kind: 'none' }
  if (typeof value !== 'string' || value.length === 0) {
    err(where, `must be a non-empty string, got ${show(value)}`)
    return null
  }
  if (value.startsWith('data:')) {
    const match = DATA_ICON_RE.exec(value)
    if (!match) {
      err(where, 'inline icon must be "data:<image/svg+xml|image/png|image/jpeg|image/webp>;base64,<padded payload>"')
      return null
    }
    const payload = match[2]
    const bytes = Buffer.from(payload, 'base64')
    if (bytes.toString('base64') !== payload) {
      err(where, 'inline icon payload is not canonically padded base64')
      return null
    }
    if (bytes.byteLength > 32 * 1024) err(where, `inline icon decodes to ${bytes.byteLength} bytes; the limit is 32 KiB`)
    return { kind: 'inline' }
  }
  // URL reference: resolution against the index URL must be https: or same-origin.
  let resolved
  try {
    resolved = new URL(value, baseUrl.href)
  } catch {
    err(where, `is neither a data: URL nor resolvable against the index URL: ${show(value)}`)
    return null
  }
  const sameOrigin = resolved.origin === baseUrl.origin
  if (!(resolved.protocol === 'https:' || sameOrigin)) {
    err(where, `resolves to ${resolved.href}, which is neither https: nor the index origin (${baseUrl.origin})`)
    return null
  }
  if (checkFiles && !value.startsWith('/') && !/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(value)) {
    const relative = decodeURIComponent(value.split(/[?#]/)[0])
    const file = path.resolve(indexDir, relative)
    if (!existsSync(file)) err(where, `relative icon file does not exist next to the index: ${path.relative(process.cwd(), file)}`)
  }
  return { kind: 'url', resolved: resolved.href }
}

// ---------------------------------------------------------------------------
// main validation
// ---------------------------------------------------------------------------

function validateSource(source, where) {
  if (!isObject(source)) {
    err(where, `required object is ${source === undefined ? 'missing' : show(source)}`)
    return
  }
  if (source.type === 'npm') {
    if (source.registry !== undefined && source.registry !== null) {
      const url = checkHttpUrl(source.registry, at(where, 'registry'), { label: 'registry URL' })
      if (url && url.pathname.length > 0 && !url.pathname.endsWith('/')) {
        // Not a hard rule, but DSH asks this registry first; a sloppy URL is a
        // silent 404 at install time.
        warn(at(where, 'registry'), `usually ends with "/": ${show(source.registry)}`)
      }
    }
    return
  }
  if (source.type === 'git') {
    if (typeof source.url !== 'string') {
      err(at(where, 'url'), 'required string is missing')
    } else {
      const url = checkHttpUrl(source.url, at(where, 'url'), { requireHttps: true, label: 'canonical https git URL' })
      if (url) {
        if (url.href !== source.url) err(at(where, 'url'), `must equal its WHATWG serialization: ${show(url.href)}`)
        const segments = url.pathname.split('/').filter(Boolean)
        if (segments.length < 2) err(at(where, 'url'), 'must contain at least two path segments (host plus owner/repo)')
        if (url.pathname.endsWith('/')) err(at(where, 'url'), 'must not end with "/"')
        if (/\.(tgz|tar\.gz)$/i.test(url.pathname)) err(at(where, 'url'), 'must not point at a .tgz/.tar.gz archive')
      }
    }
    if (typeof source.commit !== 'string') err(at(where, 'commit'), 'required string is missing')
    else if (!/^[0-9a-f]{40}$/.test(source.commit)) err(at(where, 'commit'), `must be a lowercase 40-hex commit SHA, got ${show(source.commit)}`)
    checkRelativeDirectory(source.path, at(where, 'path'))
    return
  }
  err(at(where, 'type'), `unknown source type ${show(source.type)}; expected "npm" or "git"`)
}

function validateVersion(version, where, context) {
  if (!isObject(version)) {
    err(where, `must be an object, got ${show(version)}`)
    return null
  }
  let valid = true

  // version
  if (typeof version.version !== 'string') {
    err(at(where, 'version'), 'required string is missing')
    valid = false
  } else if (!SEMVER_RE.test(version.version)) {
    err(at(where, 'version'), `is not an exact SemVer version: ${show(version.version)}`)
    valid = false
  } else {
    const sourceType = isObject(version.source) ? version.source.type : undefined
    if (sourceType === 'npm' && semver && semver.valid(version.version) !== version.version) {
      err(at(where, 'version'), `npm sources require a canonical published version (semver.valid(v) === v, no build metadata): ${show(version.version)}`)
      valid = false
    }
    context.seenVersions.set(version.version, (context.seenVersions.get(version.version) ?? 0) + 1)
    if (context.seenVersions.get(version.version) > 1) {
      err(at(where, 'version'), `duplicate exact version string ${show(version.version)} in the same plugin`)
      valid = false
    }
  }

  // publishTimestamp
  if (version.publishTimestamp === PLACEHOLDER) {
    if (context.strict) {
      err(at(where, 'publishTimestamp'), `the ${PLACEHOLDER} placeholder is still present; substitute the real Unix seconds before publishing`)
      valid = false
    } else {
      warn(at(where, 'publishTimestamp'), `${PLACEHOLDER} placeholder accepted for validation only — substitute the real Unix seconds before publishing (run with --strict to enforce)`)
    }
  } else if (version.publishTimestamp === undefined) {
    err(at(where, 'publishTimestamp'), 'required field is missing')
    valid = false
  } else if (!Number.isInteger(version.publishTimestamp)) {
    err(at(where, 'publishTimestamp'), `must be an integer Unix timestamp in seconds, got ${show(version.publishTimestamp)}`)
    valid = false
  } else if (version.publishTimestamp < 0 || version.publishTimestamp >= 1e11) {
    err(at(where, 'publishTimestamp'), `must be in [0, 10^11), got ${version.publishTimestamp}`)
    valid = false
  }

  // source
  validateSource(version.source, at(where, 'source'))

  // engines — REQUIRED by the pinned format note, including engines.dsh
  if (version.engines === undefined) {
    err(at(where, 'engines'), 'required object is missing; every listed version must declare engines.dsh')
    valid = false
  } else if (!isObject(version.engines)) {
    err(at(where, 'engines'), `must be an object, got ${show(version.engines)}`)
    valid = false
  } else if (!isNonBlank(version.engines.dsh)) {
    err(at(where, 'engines.dsh'), `required player range is missing or blank: ${show(version.engines.dsh)}`)
    valid = false
  } else if (!isValidRange(version.engines.dsh)) {
    err(at(where, 'engines.dsh'), `is not a valid npm SemVer range: ${show(version.engines.dsh)}`)
    valid = false
  }

  return valid ? version : null
}

function validatePlugin(plugin, index, context) {
  const where = at('plugins', index)
  if (!isObject(plugin)) {
    err(where, `must be an object, got ${show(plugin)}`)
    return
  }

  // name
  if (plugin.name === undefined) err(at(where, 'name'), 'required package name is missing')
  else {
    validatePackageName(plugin.name, at(where, 'name'))
    const seen = context.seenNames.get(plugin.name)
    if (seen !== undefined) err(at(where, 'name'), `duplicate name ${show(plugin.name)} (already used by plugins[${seen}]); names must be unique in the index`)
    else context.seenNames.set(plugin.name, index)
  }

  checkLocalizedText(plugin.title, at(where, 'title'))
  checkLocalizedText(plugin.description, at(where, 'description'))

  if (plugin.author !== undefined && !isNonBlank(plugin.author)) {
    err(at(where, 'author'), 'must be a string with at least one non-whitespace character')
  }

  if (plugin.homepage !== undefined) {
    checkHttpUrl(plugin.homepage, at(where, 'homepage'), { label: 'homepage URL', allowQuery: true, allowHash: true })
  }

  if (plugin.repository !== undefined) {
    if (!isObject(plugin.repository)) err(at(where, 'repository'), `must be an object {url, directory?}, got ${show(plugin.repository)}`)
    else {
      if (typeof plugin.repository.url !== 'string') err(at(where, 'repository.url'), 'required string is missing')
      else {
        const url = checkHttpUrl(plugin.repository.url, at(where, 'repository.url'), { label: 'repository web URL' })
        if (url && /\.git$/.test(url.pathname)) warn(at(where, 'repository.url'), 'is a Git transport URL; the format wants the viewable web page URL')
      }
      checkRelativeDirectory(plugin.repository.directory, at(where, 'repository.directory'))
    }
  }

  const icon = checkIcon(plugin.icon, at(where, 'icon'), context.baseUrl, context)

  // metadata
  if (plugin.metadata !== undefined) {
    const metaWhere = at(where, 'metadata')
    if (!isObject(plugin.metadata)) err(metaWhere, `must be an object, got ${show(plugin.metadata)}`)
    else {
      if (plugin.metadata.category !== undefined && !context.categories.has(plugin.metadata.category)) {
        err(at(metaWhere, 'category'), `refers to undeclared category ${show(plugin.metadata.category)}`)
      }
      if (plugin.metadata.labels !== undefined) {
        if (!Array.isArray(plugin.metadata.labels)) err(at(metaWhere, 'labels'), 'must be an array of declared label ids')
        else {
          const seen = new Set()
          plugin.metadata.labels.forEach((label, i) => {
            if (!context.labels.has(label)) err(at(at(metaWhere, 'labels'), i), `refers to undeclared label ${show(label)}`)
            if (seen.has(label)) err(at(at(metaWhere, 'labels'), i), `duplicate label ${show(label)}`)
            seen.add(label)
          })
        }
      }
      if (plugin.metadata.keywords !== undefined) {
        if (!Array.isArray(plugin.metadata.keywords)) err(at(metaWhere, 'keywords'), 'must be an array of strings')
        else plugin.metadata.keywords.forEach((kw, i) => {
          if (typeof kw !== 'string') err(at(at(metaWhere, 'keywords'), i), `must be a string, got ${show(kw)}`)
        })
      }
      if (plugin.metadata.sortKeys !== undefined) {
        if (!isObject(plugin.metadata.sortKeys)) err(at(metaWhere, 'sortKeys'), 'must be an object of declared sort-key ids → number')
        else {
          for (const [key, value] of Object.entries(plugin.metadata.sortKeys)) {
            if (!context.sortKeys.has(key)) err(at(at(metaWhere, 'sortKeys'), key), `refers to undeclared sort key ${show(key)}`)
            if (typeof value !== 'number' || !Number.isFinite(value)) err(at(at(metaWhere, 'sortKeys'), key), `must be a finite number, got ${show(value)}`)
          }
        }
      }
    }
  }

  // versions
  const versionResults = []
  if (!Array.isArray(plugin.versions)) {
    err(at(where, 'versions'), `required non-empty array is missing or is ${show(plugin.versions)}`)
  } else if (plugin.versions.length === 0) {
    err(at(where, 'versions'), 'required non-empty array has no entries')
  } else {
    const versionContext = { ...context, seenVersions: new Map() }
    plugin.versions.forEach((version, i) => {
      const result = validateVersion(version, at(at(where, 'versions'), i), versionContext)
      if (result) versionResults.push(result)
    })
  }

  // dist-tags
  if (plugin['dist-tags'] !== undefined) {
    const tagsWhere = at(where, 'dist-tags')
    if (!isObject(plugin['dist-tags'])) err(tagsWhere, `must be an object, got ${show(plugin['dist-tags'])}`)
    else {
      const listed = new Set((plugin.versions ?? []).filter(isObject).map((v) => v.version))
      for (const [tag, target] of Object.entries(plugin['dist-tags'])) {
        if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(tag)) err(at(tagsWhere, tag), `is not a usable npm distribution-tag name`)
        else if (semver && semver.valid(tag) !== null) err(at(tagsWhere, tag), `is a version, not a distribution tag`)
        else if (semver && semver.validRange(tag) !== null) warn(at(tagsWhere, tag), `looks like a SemVer range, not a distribution tag`)
        if (!listed.has(target)) err(at(tagsWhere, tag), `points at ${show(target)}, which is not an exact listed version of this plugin`)
      }
    }
  }

  return { name: plugin.name, icon, versions: versionResults }
}

function crossCheckPackageJson(indexDir, plugins, { strict }) {
  const manifestPath = path.resolve(indexDir, '..', 'package.json')
  if (!existsSync(manifestPath)) {
    warn('cross-check', `no package.json at ${path.relative(process.cwd(), manifestPath)}; skipped manifest cross-check`)
    return
  }
  let manifest
  try {
    manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  } catch (error) {
    warn('cross-check', `could not read ${path.relative(process.cwd(), manifestPath)}: ${error.message}`)
    return
  }
  const entry = plugins.find((plugin) => isObject(plugin) && plugin.name === manifest.name)
  if (!entry) {
    err('cross-check', `package.json declares name ${show(manifest.name)} but the index has no plugin entry with that name`)
    return
  }
  const versions = (entry.versions ?? []).filter((v) => isObject(v) && typeof v.version === 'string')
  const listed = new Set(versions.map((v) => v.version))
  if (!listed.has(manifest.version)) {
    err('cross-check', `the index lists ${[...listed].join(', ') || '(nothing)'} but package.json is at ${manifest.version}; publish that version and list it, or bump the index`)
  }
  if (versions.length > 0) {
    const highest = versions
      .map((v) => v.version)
      .sort((a, b) => (semver ? semver.rcompare(a, b) : b.localeCompare(a)))[0]
    if (highest !== manifest.version) {
      warn('cross-check', `highest listed version ${highest} differs from package.json version ${manifest.version}`)
    }
  }
  const manifestRange = manifest.engines?.dsh
  if (manifestRange === undefined) {
    warn('cross-check', 'package.json declares no engines.dsh; a market version is checked against that declaration at install time')
  } else {
    const match = versions.find((v) => v.version === manifest.version)
    if (match && isObject(match.engines) && match.engines.dsh !== undefined && match.engines.dsh !== manifestRange) {
      err('cross-check', `engines.dsh mismatch: index has ${show(match.engines.dsh)}, package.json has ${show(manifestRange)} (the format wants it copied unchanged)`)
    } else if (match && isObject(match.engines) && match.engines.dsh === manifestRange) {
      notes.push(`engines.dsh matches package.json: ${show(manifestRange)}`)
    }
  }
  if (manifest.dsh?.bundle?.patch === undefined) {
    warn('cross-check', 'package.json declares no dsh.bundle.patch; installation refuses a package without a bundle patch')
  } else {
    notes.push(`package.json declares dsh.bundle.patch: ${show(manifest.dsh.bundle.patch)}`)
  }
  // repository/homepage drift is display-only, so it is a warning.
  const manifestRepo = manifest.repository?.url ?? manifest.repository
  if (isObject(entry.repository) && typeof manifestRepo === 'string') {
    const normalize = (url) => url.replace(/^git\+/, '').replace(/\.git$/, '').replace(/\/$/, '')
    if (normalize(manifestRepo) !== normalize(entry.repository.url)) {
      warn('cross-check', `repository.url ${show(entry.repository.url)} differs from package.json ${show(manifestRepo)}`)
    }
  }
  if (isObject(entry.repository) && entry.repository.directory !== undefined && strict) {
    notes.push(`repository.directory is ${show(entry.repository.directory)} — keep it only while the package really lives in that subdirectory`)
  }
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const options = {
    indexPath: DEFAULT_INDEX,
    baseUrl: DEFAULT_BASE_URL,
    dshVersion: DEFAULT_DSH_VERSION,
    strict: false,
    packageCheck: true,
    iconFiles: true,
  }
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === '-h' || arg === '--help') return { help: true }
    else if (arg === '--strict') options.strict = true
    else if (arg === '--no-package-check') options.packageCheck = false
    else if (arg === '--no-icon-files') options.iconFiles = false
    else if (arg.startsWith('--base-url=')) options.baseUrl = arg.slice('--base-url='.length)
    else if (arg === '--base-url') options.baseUrl = argv[++i]
    else if (arg.startsWith('--dsh-version=')) options.dshVersion = arg.slice('--dsh-version='.length)
    else if (arg === '--dsh-version') options.dshVersion = argv[++i]
    else if (arg.startsWith('-')) throw new Error(`unknown option ${arg}`)
    else options.indexPath = arg
  }
  if (!options.baseUrl) throw new Error('--base-url needs a value')
  if (!options.dshVersion) throw new Error('--dsh-version needs a value')
  return options
}

const HELP = `verify-index.mjs — validate a DSH plugin-market index (format 1)

Usage: node .release/verify-index.mjs [indexPath] [options]

  --base-url <url>    URL the index will be served from (default ${DEFAULT_BASE_URL})
  --dsh-version <v>   DSH version to test engines.dsh against (default ${DEFAULT_DSH_VERSION})
  --strict            Reject the ${PLACEHOLDER} placeholder (publish build)
  --no-package-check  Skip the ../package.json cross-check
  --no-icon-files     Skip the on-disk existence check for relative icons
  -h, --help          Show this help

Exit codes: 0 pass, 1 validation errors, 2 usage/IO error.`

function main(argv) {
  const options = parseArgs(argv)
  if (options.help) {
    console.log(HELP)
    return 0
  }

  const indexPath = path.resolve(options.indexPath)
  const indexDir = path.dirname(indexPath)
  if (!existsSync(indexPath)) throw new Error(`index file does not exist: ${indexPath}`)

  const label = path.relative(process.cwd(), indexPath) || indexPath
  const bytes = statSync(indexPath).size
  if (bytes > MAX_INDEX_BYTES) err(label, `index is ${bytes} bytes; the reader bounds it at ${MAX_INDEX_BYTES} bytes`)

  const buffer = readFileSync(indexPath)
  if (buffer[0] === 0xef && buffer[1] === 0xbb && buffer[2] === 0xbf) {
    err(label, 'index starts with a UTF-8 BOM; serve it without a BOM')
  }
  let raw
  try {
    raw = new TextDecoder('utf-8', { fatal: true }).decode(buffer)
  } catch {
    throw new Error(`${indexPath} is not valid UTF-8`)
  }

  let index
  try {
    index = JSON.parse(raw)
  } catch (error) {
    throw new Error(`${indexPath} is not valid JSON: ${error.message}`)
  }

  if (!isObject(index)) throw new Error(`${indexPath} must contain a JSON object`)
  if (index.format !== 1) err('format', `must be the integer 1, got ${show(index.format)}`)

  checkLocalizedText(index.title, 'title', { required: true })
  checkLocalizedText(index.description, 'description')

  const context = {
    strict: options.strict,
    baseUrl: new URL(options.baseUrl),
    checkFiles: options.iconFiles,
    indexDir,
    seenNames: new Map(),
    categories: new Set(),
    labels: new Set(),
    sortKeys: new Set(),
  }
  if (!/^https?:$/.test(context.baseUrl.protocol)) throw new Error(`--base-url must be http: or https:, got ${context.baseUrl.href}`)

  if (index.metadata !== undefined) {
    if (!isObject(index.metadata)) err('metadata', `must be an object, got ${show(index.metadata)}`)
    else {
      const declarations = [
        ['categories', context.categories, (v, where) => {
          if (!isObject(v)) err(where, `must be an object, got ${show(v)}`)
          else if (isObject(v.title) || typeof v.title === 'string') checkLocalizedText(v.title, at(where, 'title'), { required: true })
          else err(at(where, 'title'), 'required LocalizedText is missing')
        }],
        ['labels', context.labels, (v, where) => {
          if (isObject(v.title) || typeof v.title === 'string') checkLocalizedText(v.title, at(where, 'title'), { required: true })
          else err(at(where, 'title'), 'required LocalizedText is missing')
        }],
        ['sortKeys', context.sortKeys, (v, where) => {
          if (isObject(v.title) || typeof v.title === 'string') checkLocalizedText(v.title, at(where, 'title'), { required: true })
          else err(at(where, 'title'), 'required LocalizedText is missing')
          if (v.order !== undefined && v.order !== 'asc' && v.order !== 'desc') err(at(where, 'order'), `must be "asc" or "desc", got ${show(v.order)}`)
        }],
      ]
      for (const [field, idSet, check] of declarations) {
        const map = index.metadata[field]
        if (map === undefined) continue
        if (!isObject(map)) {
          err(at('metadata', field), `must be an object, got ${show(map)}`)
          continue
        }
        for (const [id, value] of Object.entries(map)) {
          if (id.length === 0) err(at('metadata', field), 'ids must be non-empty strings')
          idSet.add(id)
          if (!isObject(value)) err(at(at('metadata', field), id), `must be an object, got ${show(value)}`)
          else check(value, at(at('metadata', field), id))
        }
      }
    }
  }

  if (!Array.isArray(index.plugins)) {
    err('plugins', `required array is missing or is ${show(index.plugins)}`)
  } else {
    if (index.plugins.length === 0) warn('plugins', 'the index lists no plugins; a reader shows an empty market')
    const results = []
    index.plugins.forEach((plugin, i) => {
      const result = validatePlugin(plugin, i, context)
      if (result) results.push(result)
    })

    if (options.packageCheck) crossCheckPackageJson(indexDir, index.plugins, options)

    // Resolved install specs + icons, so the reviewer sees what users will get.
    for (const result of results) {
      if (result.icon?.kind === 'url') notes.push(`${result.name} icon → ${result.icon.resolved}`)
      for (const version of result.versions) {
        const dshRange = version.engines?.dsh
        const install = version.source?.type === 'npm' ? `${result.name}@${version.version}` : `git+${version.source?.url}#${version.source?.commit}`
        notes.push(`${result.name} ${version.version} installs as ${install}`)
        if (typeof dshRange === 'string' && isValidRange(dshRange)) {
          if (semver) {
            const compatible = semver.satisfies(options.dshVersion, dshRange, { includePrerelease: true })
            const line = `engines.dsh ${dshRange} vs DSH ${options.dshVersion} → ${compatible ? 'compatible' : 'NOT compatible'}`
            if (compatible) notes.push(line)
            else err('engines.dsh', `${line}; the install would be refused by this DSH`)
          } else {
            notes.push(`engines.dsh ${dshRange} (compatibility not evaluated: node-semver unavailable)`)
          }
        }
      }
    }
  }

  // report
  console.log(`verify-index: ${label} (served from ${options.baseUrl})`)
  for (const error of errors) console.log(`ERROR ${error}`)
  for (const warning of warnings) console.log(`WARN  ${warning}`)
  for (const note of notes) console.log(`info  ${note}`)
  if (!semver) console.log('WARN  node-semver was not found; SemVer ranges were checked by grammar only (set DSH_VERIFY_SEMVER_PATH to override)')
  const summary = `${errors.length} error(s), ${warnings.length} warning(s)`
  if (errors.length > 0) {
    console.log(`verify-index: FAIL — ${summary}`)
    return 1
  }
  console.log(`verify-index: PASS — ${summary}${options.strict ? ' [strict]' : ''}`)
  return 0
}

try {
  process.exitCode = main(process.argv.slice(2))
} catch (error) {
  console.error(`verify-index: ${error.message}`)
  console.error('Run with --help for usage.')
  process.exitCode = 2
}
