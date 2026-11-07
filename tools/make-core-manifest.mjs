#!/usr/bin/env node
/**
 * Write `core-manifest.sha256` — the SHA-256 of every file in the shipped,
 * byte-identical Antigravity plugin tree (`greatwall-agent/`).
 *
 * WHY: the whole point of this port is that the Python core is NOT modified.
 * The manifest is the evidence a user (or CI) can check with
 * `node tools/verify-core.mjs`, and it also catches an accidental edit during a
 * future sync from `plugins/greatwall-agent/` in the design repository.
 *
 * Usage: node tools/make-core-manifest.mjs
 */
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const PACKAGE_ROOT = fileURLToPath(new URL('..', import.meta.url))
const CORE_ROOT = path.join(PACKAGE_ROOT, 'greatwall-agent')
const MANIFEST = path.join(PACKAGE_ROOT, 'core-manifest.sha256')

/** Directories and files that are build/runtime noise, never shipped content. */
const IGNORED = new Set(['__pycache__', '.pytest_cache', 'node_modules'])
const IGNORED_EXTENSIONS = new Set(['.pyc', '.pyo'])

/**
 * List every shipped file of the core tree as `/`-separated relative paths.
 * @param {string} dir - absolute directory.
 * @param {string} [prefix] - relative prefix used while recursing.
 * @returns {string[]} sorted relative paths.
 */
function listFiles(dir, prefix = '') {
  const out = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (IGNORED.has(entry.name)) continue
    const rel = prefix ? prefix + '/' + entry.name : entry.name
    const abs = path.join(dir, entry.name)
    if (entry.isDirectory()) out.push(...listFiles(abs, rel))
    else if (!IGNORED_EXTENSIONS.has(path.extname(entry.name).toLowerCase())) out.push(rel)
  }
  return out.sort()
}

/**
 * SHA-256 of one file.
 * @param {string} file - absolute path.
 * @returns {string} lowercase hex digest.
 */
export function sha256(file) {
  return createHash('sha256').update(fs.readFileSync(file)).digest('hex')
}

const files = listFiles(CORE_ROOT)
const lines = files.map((rel) => `${sha256(path.join(CORE_ROOT, rel))}  ${rel}`)
fs.writeFileSync(MANIFEST, lines.join('\n') + '\n', 'utf8')
console.log(`wrote ${path.relative(PACKAGE_ROOT, MANIFEST)}: ${files.length} files`)
