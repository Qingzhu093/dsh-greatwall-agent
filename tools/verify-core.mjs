#!/usr/bin/env node
/**
 * Verify the shipped `greatwall-agent/` tree against `core-manifest.sha256`.
 *
 * The DSH port ships the original Antigravity plugin byte-for-byte; this script
 * is the machine-checkable proof. Exit code 0 = identical, 1 = drift, missing
 * file, or unexpected extra file.
 *
 * Usage:
 *   node tools/verify-core.mjs             # verify against the shipped manifest
 *   node tools/verify-core.mjs --json      # machine-readable result
 */
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const PACKAGE_ROOT = fileURLToPath(new URL('..', import.meta.url))
const CORE_ROOT = path.join(PACKAGE_ROOT, 'greatwall-agent')
const MANIFEST = path.join(PACKAGE_ROOT, 'core-manifest.sha256')
const JSON_OUTPUT = process.argv.includes('--json')

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
 * Parse `core-manifest.sha256`.
 * @param {string} text - manifest content.
 * @returns {Map<string, string>} relative path -> expected digest.
 */
function parseManifest(text) {
  const expected = new Map()
  for (const line of text.split(/\r?\n/)) {
    if (line.trim().length === 0) continue
    const match = /^([0-9a-f]{64}) {2}(.+)$/.exec(line)
    if (!match) throw new Error('malformed manifest line: ' + line)
    expected.set(match[2], match[1])
  }
  return expected
}

const problems = []
const expected = parseManifest(fs.readFileSync(MANIFEST, 'utf8'))
const actual = new Set(listFiles(CORE_ROOT))

for (const [rel, digest] of expected) {
  if (!actual.has(rel)) {
    problems.push({ kind: 'missing', path: rel })
    continue
  }
  const got = createHash('sha256').update(fs.readFileSync(path.join(CORE_ROOT, rel))).digest('hex')
  if (got !== digest) problems.push({ kind: 'modified', path: rel, expected: digest, actual: got })
}
for (const rel of actual) {
  if (!expected.has(rel)) problems.push({ kind: 'extra', path: rel })
}

const result = { ok: problems.length === 0, files: expected.size, problems }
if (JSON_OUTPUT) {
  process.stdout.write(JSON.stringify(result, null, 2) + '\n')
} else if (result.ok) {
  console.log(`OK: ${result.files} core files match core-manifest.sha256 (byte-identical Antigravity tree)`)
} else {
  console.error(`FAIL: ${problems.length} problem(s) in the shipped core tree`)
  for (const problem of problems) {
    if (problem.kind === 'modified') console.error(`  modified  ${problem.path}\n            expected ${problem.expected}\n            actual   ${problem.actual}`)
    else console.error(`  ${problem.kind.padEnd(8)}  ${problem.path}`)
  }
  console.error('The Python core must stay byte-identical to plugins/greatwall-agent/ in the design repo.')
}
process.exit(result.ok ? 0 : 1)
