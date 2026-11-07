#!/usr/bin/env node
/**
 * finalize-index.mjs — substitute the `__PUBLISH_TIMESTAMP__` placeholder in the
 * market index with the REAL publish time recorded by the npm registry.
 *
 * Why this exists: `publishTimestamp` must be an integer Unix timestamp in
 * `[0, 10^11)` (format-1 rule), but market/index.json is committed before the npm
 * release exists, so it carries the literal token. Typing the timestamp by hand
 * is the easiest place to publish a wrong index, so the substitution is scripted
 * and reads the number from the registry document:
 *
 *   GET https://registry.npmjs.org/dsh-greatwall-agent   →   { "time": { "4.2.0": "2026-11-…T…Z", … } }
 *
 * Dry run by default. Nothing is written without --write.
 *
 * Usage:
 *   node .release/finalize-index.mjs                       # show what would change
 *   node .release/finalize-index.mjs --write               # substitute + save
 *   node .release/finalize-index.mjs --timestamp 1790476800 --write   # offline
 *   node .release/finalize-index.mjs --version 4.2.0 --index <path>
 *
 * Exit codes: 0 done or nothing to do, 1 failed, 2 usage error.
 */

import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const PLACEHOLDER = '__PUBLISH_TIMESTAMP__'
const DEFAULT_INDEX = fileURLToPath(new URL('../market/index.json', import.meta.url))
const DEFAULT_REGISTRY = 'https://registry.npmjs.org/'
const MAX_TIMESTAMP = 1e11

const HELP = `finalize-index.mjs — substitute ${PLACEHOLDER} with the real npm publish time

Usage: node .release/finalize-index.mjs [options]

  --index <path>       index to edit (default: market/index.json of this package)
  --package <name>     npm package name (default: the index entry's name)
  --version <semver>   version to read the publish time for (default: the entry
                       whose publishTimestamp is still the placeholder)
  --timestamp <unix>   use this integer instead of asking the registry (offline)
  --registry <url>     registry to ask (default: ${DEFAULT_REGISTRY})
  --write              write the file (without this it is a dry run)
  -h, --help           show this help

Exit codes: 0 done or nothing to do, 1 failed, 2 usage error.`

function parseArgs(argv) {
  const options = { indexPath: DEFAULT_INDEX, write: false }
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === '-h' || arg === '--help') return { help: true }
    else if (arg === '--write') options.write = true
    else if (arg === '--index') options.indexPath = argv[++i]
    else if (arg.startsWith('--index=')) options.indexPath = arg.slice('--index='.length)
    else if (arg === '--package') options.packageName = argv[++i]
    else if (arg.startsWith('--package=')) options.packageName = arg.slice('--package='.length)
    else if (arg === '--version') options.version = argv[++i]
    else if (arg.startsWith('--version=')) options.version = arg.slice('--version='.length)
    else if (arg === '--timestamp') options.timestamp = argv[++i]
    else if (arg.startsWith('--timestamp=')) options.timestamp = arg.slice('--timestamp='.length)
    else if (arg === '--registry') options.registry = argv[++i]
    else if (arg.startsWith('--registry=')) options.registry = arg.slice('--registry='.length)
    else throw new Error(`unknown option ${arg}`)
  }
  return options
}

/**
 * Ask the npm registry for the publish time of one version, in Unix seconds.
 * Uses the registry document directly (`<registry>/<name>`) rather than shelling
 * out to `npm view`, so there is no shell quoting and no Node `.cmd` spawn issue
 * on Windows.
 */
async function timestampFromRegistry(packageName, version, registry) {
  const base = (registry ?? DEFAULT_REGISTRY).replace(/\/+$/, '')
  // Registry path encoding for a scoped name is `@scope%2fname`.
  const encoded = packageName.startsWith('@') ? packageName.replace('/', '%2f') : encodeURIComponent(packageName)
  const url = `${base}/${encoded}`

  let response
  try {
    response = await fetch(url, {
      headers: { accept: 'application/json' },
      signal: AbortSignal.timeout(30_000),
    })
  } catch (error) {
    throw new Error(`could not reach ${url}: ${error.message}`)
  }
  if (response.status === 404) {
    throw new Error(
      `${packageName} is not in ${base} yet (HTTP 404 for ${url}). ` +
        'Publish it first, or pass --timestamp <unix-seconds>.',
    )
  }
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status} ${response.statusText}`)

  let document
  try {
    document = await response.json()
  } catch {
    throw new Error(`${url} did not return JSON`)
  }
  const published = document?.time?.[version]
  if (!published) {
    throw new Error(
      `${packageName}@${version} is not in the registry yet (no "time" entry). ` +
        'Publish it first, or pass --timestamp <unix-seconds>.',
    )
  }
  const millis = Date.parse(published)
  if (!Number.isFinite(millis)) throw new Error(`registry returned an unparseable time for ${version}: ${published}`)
  return { seconds: Math.floor(millis / 1000), iso: new Date(millis).toISOString(), from: `registry ${url}` }
}

async function main(argv) {
  const options = parseArgs(argv)
  if (options.help) {
    console.log(HELP)
    return 0
  }

  const indexPath = path.resolve(options.indexPath)
  if (!existsSync(indexPath)) throw new Error(`index not found: ${indexPath}`)
  const original = readFileSync(indexPath, 'utf8')
  const index = JSON.parse(original)

  const pending = []
  for (const plugin of index.plugins ?? []) {
    for (const version of plugin.versions ?? []) {
      if (version.publishTimestamp === PLACEHOLDER) pending.push({ plugin, version })
    }
  }

  if (pending.length === 0) {
    console.log(`finalize-index: ${path.relative(process.cwd(), indexPath)} has no ${PLACEHOLDER} left; nothing to do`)
    return 0
  }

  const selected = options.version ? pending.filter((entry) => entry.version.version === options.version) : pending
  if (selected.length === 0) {
    throw new Error(`no pending placeholder for version ${options.version}; pending: ${pending.map((e) => e.version.version).join(', ')}`)
  }

  const results = []
  for (const entry of selected) {
    if (options.timestamp !== undefined) {
      const seconds = Number(options.timestamp)
      if (!Number.isInteger(seconds)) throw new Error(`--timestamp must be an integer, got ${options.timestamp}`)
      results.push({ entry, seconds, iso: new Date(seconds * 1000).toISOString(), source: '--timestamp' })
      continue
    }
    const packageName = options.packageName ?? entry.plugin.name
    if (!packageName) throw new Error('could not determine the package name; pass --package')
    const { seconds, iso, from } = await timestampFromRegistry(packageName, entry.version.version, options.registry)
    results.push({ entry, seconds, iso, source: from })
  }

  for (const result of results) {
    if (!Number.isInteger(result.seconds) || result.seconds < 0 || result.seconds >= MAX_TIMESTAMP) {
      throw new Error(`timestamp ${result.seconds} is outside the allowed [0, 10^11) range`)
    }
    result.entry.version.publishTimestamp = result.seconds
    console.log(
      `finalize-index: ${result.entry.plugin.name}@${result.entry.version.version} publishTimestamp ` +
        `${PLACEHOLDER} → ${result.seconds}  (${result.iso}, from ${result.source})`,
    )
  }

  if (pending.length !== selected.length) {
    const remaining = pending.length - selected.length
    console.log(`finalize-index: ${remaining} placeholder(s) left for other versions; this file cannot pass --strict yet`)
  }

  const serialized = `${JSON.stringify(index, null, 2)}\n`
  if (!options.write) {
    const before = original.split('\n').filter((line) => line.includes(PLACEHOLDER)).length
    console.log(`finalize-index: DRY RUN — ${before} placeholder line(s) in ${path.relative(process.cwd(), indexPath)}`)
    console.log('finalize-index: re-run with --write, then: node .release/verify-index.mjs --strict')
    return 0
  }

  writeFileSync(indexPath, serialized, 'utf8')
  console.log(`finalize-index: wrote ${path.relative(process.cwd(), indexPath)} (${serialized.length} bytes)`)
  console.log('finalize-index: next → node .release/verify-index.mjs --strict')
  return 0
}

try {
  process.exitCode = await main(process.argv.slice(2))
} catch (error) {
  console.error(`finalize-index: ${error.message}`)
  process.exitCode = 1
}
