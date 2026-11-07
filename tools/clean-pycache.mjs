#!/usr/bin/env node
/**
 * Remove Python bytecode caches from the shipped core tree.
 *
 * WHY: `package.json` `files` lists the whole `greatwall-agent/` directory, and a
 * `files` whitelist wins over `.gitignore`, so `__pycache__/*.pyc` created by any
 * local run of the MCP server WOULD be packed into the npm tarball. `prepack`
 * runs this automatically for `npm pack` and `npm publish`; the runtime also sets
 * `PYTHONDONTWRITEBYTECODE=1` (lib/index.js) so the caches are not recreated
 * inside an installed package in the first place.
 *
 * Usage: node tools/clean-pycache.mjs [--dry-run]
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const PACKAGE_ROOT = fileURLToPath(new URL('..', import.meta.url))
const CORE_ROOT = path.join(PACKAGE_ROOT, 'greatwall-agent')
const DRY_RUN = process.argv.includes('--dry-run')

/**
 * Delete `__pycache__` directories and stray `.pyc`/`.pyo` files under a tree.
 * @param {string} dir - absolute directory to walk.
 * @returns {string[]} removed (or would-be-removed) paths, relative to the package root.
 */
function clean(dir) {
  const removed = []
  if (!fs.existsSync(dir)) return removed
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === '__pycache__' || entry.name === '.pytest_cache') {
        removed.push(path.relative(PACKAGE_ROOT, abs).replace(/\\/g, '/'))
        if (!DRY_RUN) fs.rmSync(abs, { recursive: true, force: true })
        continue
      }
      removed.push(...clean(abs))
    } else if (/\.py[co]$/i.test(entry.name)) {
      removed.push(path.relative(PACKAGE_ROOT, abs).replace(/\\/g, '/'))
      if (!DRY_RUN) fs.rmSync(abs, { force: true })
    }
  }
  return removed
}

const removed = clean(CORE_ROOT)
const action = DRY_RUN ? 'would remove' : 'removed'
// Diagnostics go to stderr on purpose: `npm pack --dry-run --json` runs prepack
// and merges script stdout into its own output, which would break JSON consumers
// (e.g. .release/verify-pack.ps1).
if (removed.length === 0) console.error(`clean-pycache: nothing to ${DRY_RUN ? 'remove' : 'clean'}`)
else console.error(`clean-pycache: ${action} ${removed.length} path(s)\n  ` + removed.join('\n  '))
