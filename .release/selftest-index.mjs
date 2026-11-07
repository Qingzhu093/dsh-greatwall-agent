#!/usr/bin/env node
/**
 * selftest-index.mjs — proves verify-index.mjs actually rejects bad indexes.
 *
 * Each case deep-copies the real market/index.json, breaks exactly one documented
 * format-1 rule in a temp file, and asserts the validator exits 1 with a message
 * that names the offending JSON path. Two control cases assert the delivered
 * index itself passes (and that --strict rejects the publish placeholder).
 *
 * Usage: node .release/selftest-index.mjs
 * Exit codes: 0 all cases behaved, 1 a case did not.
 */

import { spawnSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const VERIFY = fileURLToPath(new URL('./verify-index.mjs', import.meta.url))
const INDEX = fileURLToPath(new URL('../market/index.json', import.meta.url))
const baseline = JSON.parse(readFileSync(INDEX, 'utf8'))
const scratch = mkdtempSync(path.join(tmpdir(), 'dsh-index-selftest-'))

/** Run the validator on a document; returns {status, output}. */
function run(document, extraArgs = [], { iconFiles = false } = {}) {
  const file = path.join(scratch, `case-${Math.random().toString(36).slice(2)}.json`)
  writeFileSync(file, typeof document === 'string' ? document : JSON.stringify(document, null, 2))
  const args = [VERIFY, file, '--no-package-check', ...extraArgs]
  if (!iconFiles) args.push('--no-icon-files')
  const result = spawnSync(process.execPath, args, { encoding: 'utf8' })
  return { status: result.status, output: `${result.stdout ?? ''}${result.stderr ?? ''}` }
}

const clone = () => JSON.parse(JSON.stringify(baseline))
const version = (doc) => doc.plugins[0].versions[0]

/** Break one rule; `mutate` receives a fresh clone. */
const CASES = [
  { why: 'format must be the integer 1', mutate: (d) => { d.format = 2 }, expect: 'format: must be the integer 1', status: 1 },
  { why: 'format as a string "1" is rejected', mutate: (d) => { d.format = '1' }, expect: 'format: must be the integer 1', status: 1 },
  { why: 'market title object must contain en', mutate: (d) => { d.title = { zh: '长城 Agent' } }, expect: 'title: a LocalizedText object must contain "en"', status: 1 },
  { why: 'market title is required', mutate: (d) => { delete d.title }, expect: 'title: required LocalizedText is missing', status: 1 },
  { why: 'language ids must be lowercase', mutate: (d) => { d.title = { en: 'M', 'zh-CN': '长' } }, expect: '"zh-CN" is not a lowercase language id', status: 1 },
  { why: 'whitespace-only LocalizedText', mutate: (d) => { d.description = { en: '   ' } }, expect: 'description.en: must contain at least one non-whitespace character', status: 1 },
  { why: 'plugin name is required', mutate: (d) => { delete d.plugins[0].name }, expect: 'plugins[0].name: required package name is missing', status: 1 },
  { why: 'plugin names must be lowercase npm names', mutate: (d) => { d.plugins[0].name = 'DSH-Greatwall-Agent' }, expect: 'plugins[0].name: is not a valid npm package name', status: 1 },
  { why: 'names must be unique', mutate: (d) => { d.plugins.push(clone().plugins[0]) }, expect: 'plugins[1].name: duplicate name "dsh-greatwall-agent"', status: 1 },
  { why: 'versions must be a non-empty array', mutate: (d) => { d.plugins[0].versions = [] }, expect: 'plugins[0].versions: required non-empty array has no entries', status: 1 },
  { why: 'version must be exact SemVer', mutate: (d) => { version(d).version = '4.2' }, expect: 'plugins[0].versions[0].version: is not an exact SemVer version', status: 1 },
  { why: 'version strings must be unique', mutate: (d) => { d.plugins[0].versions.push(clone().plugins[0].versions[0]) }, expect: 'plugins[0].versions[1].version: duplicate exact version string', status: 1 },
  { why: 'publishTimestamp must be an integer', mutate: (d) => { version(d).publishTimestamp = 1.5 }, expect: 'plugins[0].versions[0].publishTimestamp: must be an integer', status: 1 },
  { why: 'publishTimestamp must be a number, not a date string', mutate: (d) => { version(d).publishTimestamp = '2026-11-07T00:00:00Z' }, expect: 'plugins[0].versions[0].publishTimestamp: must be an integer', status: 1 },
  { why: 'publishTimestamp stays under 10^11', mutate: (d) => { version(d).publishTimestamp = 1e12 }, expect: 'must be in [0, 10^11)', status: 1 },
  { why: 'source.type must be npm or git', mutate: (d) => { version(d).source = { type: 'tarball' } }, expect: 'plugins[0].versions[0].source.type: unknown source type "tarball"', status: 1 },
  { why: 'engines is required by the pinned note', mutate: (d) => { delete version(d).engines }, expect: 'plugins[0].versions[0].engines: required object is missing', status: 1 },
  { why: 'engines.dsh is required', mutate: (d) => { version(d).engines = {} }, expect: 'plugins[0].versions[0].engines.dsh: required player range is missing or blank', status: 1 },
  { why: 'engines.dsh must be a valid range', mutate: (d) => { version(d).engines.dsh = '>=0.2.2-rc.1 <<< 0.3.0' }, expect: 'is not a valid npm SemVer range', status: 1 },
  { why: 'engines.dsh must accept the running DSH', mutate: (d) => { version(d).engines.dsh = '>=99.0.0' }, expect: 'engines.dsh: engines.dsh >=99.0.0 vs DSH 0.2.2-rc.1 → NOT compatible', status: 1 },
  { why: 'dist-tags target must be a listed version', mutate: (d) => { d.plugins[0]['dist-tags'] = { latest: '9.9.9' } }, expect: 'plugins[0].dist-tags.latest: points at "9.9.9", which is not an exact listed version', status: 1 },
  { why: 'dist-tags keys cannot be versions', mutate: (d) => { d.plugins[0]['dist-tags'] = { '4.2.0': '4.2.0' } }, expect: 'is a version, not a distribution tag', status: 1 },
  { why: 'repository.url must be a web URL', mutate: (d) => { d.plugins[0].repository = { url: 'git@github.com:Qingzhu093/dsh-greatwall-agent.git' } }, expect: 'plugins[0].repository.url: is not an absolute repository web URL', status: 1 },
  { why: 'repository.url forbids fragments', mutate: (d) => { d.plugins[0].repository = { url: 'https://github.com/a/b#readme' } }, expect: 'plugins[0].repository.url: must not contain a fragment', status: 1 },
  { why: 'repository.directory must be relative', mutate: (d) => { d.plugins[0].repository.directory = '/abs/path' }, expect: 'plugins[0].repository.directory: must be a relative "/"-separated path', status: 1 },
  { why: 'repository.directory forbids "." segments', mutate: (d) => { d.plugins[0].repository.directory = './pkg' }, expect: 'must not contain "." or ".." segments', status: 1 },
  { why: 'author cannot be blank', mutate: (d) => { d.plugins[0].author = '  ' }, expect: 'plugins[0].author: must be a string with at least one non-whitespace character', status: 1 },
  { why: 'relative icon must exist next to the index', mutate: () => {}, expect: 'relative icon file does not exist next to the index', status: 1, iconFiles: true },
  { why: 'undeclared category is rejected', mutate: (d) => { d.plugins[0].metadata = { category: 'nope' } }, expect: 'plugins[0].metadata.category: refers to undeclared category "nope"', status: 1 },
  { why: 'git source needs a 40-hex commit', mutate: (d) => { version(d).source = { type: 'git', url: 'https://github.com/a/b', commit: 'abc123' } }, expect: 'commit: must be a lowercase 40-hex commit SHA', status: 1 },
  { why: 'git source url must be https', mutate: (d) => { version(d).source = { type: 'git', url: 'http://github.com/a/b', commit: 'a'.repeat(40) } }, expect: 'must use https:', status: 1 },
  { why: 'git source url must not end with .git/.tar.gz', mutate: (d) => { version(d).source = { type: 'git', url: 'https://github.com/a/b.tar.gz', commit: 'a'.repeat(40) } }, expect: 'must not point at a .tgz/.tar.gz archive', status: 1 },
  { why: 'inline icon must be canonical base64', mutate: (d) => { d.plugins[0].icon = 'data:image/svg+xml;base64,AAA' }, expect: 'inline icon payload is not canonically padded base64', status: 1 },
  { why: 'inline icon must be an allowed image type', mutate: (d) => { d.plugins[0].icon = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=' }, expect: 'inline icon must be "data:<image/svg+xml|image/png|image/jpeg|image/webp>;base64,', status: 1 },
  { why: 'inline icon is capped at 32 KiB', mutate: (d) => { d.plugins[0].icon = `data:image/png;base64,${Buffer.alloc(33 * 1024).toString('base64')}` }, expect: 'the limit is 32 KiB', status: 1 },
  { why: 'cross-origin http icons are rejected', mutate: (d) => { d.plugins[0].icon = 'http://evil.example/x.svg' }, expect: 'neither https: nor the index origin', status: 1 },
  { why: 'index must be valid JSON', mutate: undefined, raw: '{ "format": 1, ', expect: 'is not valid JSON', status: 2 },
  { why: 'a BOM is rejected', raw: `\uFEFF${JSON.stringify(baseline)}`, expect: 'starts with a UTF-8 BOM', status: 1 },
]

let failures = 0
console.log(`selftest-index: ${CASES.length + 2} cases against ${path.basename(VERIFY)}`)

// Control case 1: the delivered index passes (placeholder reported as a warning).
{
  const { status, output } = run(baseline)
  const ok = status === 0 && output.includes('PASS') && output.includes('__PUBLISH_TIMESTAMP__')
  report('control: delivered index passes with a placeholder warning', ok, status, output)
}

// Control case 2: --strict refuses the placeholder.
{
  const { status, output } = run(baseline, ['--strict'])
  const ok = status === 1 && output.includes('placeholder is still present')
  report('control: --strict refuses __PUBLISH_TIMESTAMP__', ok, status, output)
}

for (const testCase of CASES) {
  let document
  if (testCase.raw !== undefined) document = testCase.raw
  else {
    document = clone()
    testCase.mutate(document)
  }
  const args = []
  if (testCase.iconFiles) args.push('--base-url', 'https://qingzhu093.github.io/x/index.json')
  const { status, output } = run(document, args, { iconFiles: testCase.iconFiles === true })
  const ok = status === testCase.status && output.includes(testCase.expect)
  report(testCase.why, ok, status, output, testCase.expect)
}

function report(why, ok, status, output, expect) {
  if (ok) {
    console.log(`ok   ${why}`)
    return
  }
  failures += 1
  console.log(`FAIL ${why} (exit ${status}, expected ${expect ? 'the message below' : '0'})`)
  if (expect && !output.includes(expect)) console.log(`     missing expected text: ${JSON.stringify(expect)}`)
  console.log(output.trimEnd().split('\n').map((line) => `     | ${line}`).join('\n'))
}

rmSync(scratch, { recursive: true, force: true })
if (failures > 0) {
  console.log(`selftest-index: FAIL — ${failures} case(s) did not behave`)
  process.exitCode = 1
} else {
  console.log('selftest-index: PASS')
  process.exitCode = 0
}
