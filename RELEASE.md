# RELEASE.md — release runbook for `dsh-greatwall-agent`

Everything below is ordered and runnable in **PowerShell 7 on Windows** from the design repo.
Nothing here was executed by the release engineer: `npm publish`, `git push`, `gh repo create`,
`gh issue create` and Pages enablement are **Lead actions** by instruction. What *was* executed
and its exact output is recorded in §0 and §11.

| Fact | Value |
| --- | --- |
| Package root | `plugins/dsh-greatwall-agent` |
| npm package | `dsh-greatwall-agent` @ `4.2.0` |
| npm user / registry | `ripplesseeing` / `https://registry.npmjs.org/` |
| GitHub owner | `Qingzhu093`, repo `dsh-greatwall-agent` (does not exist yet) |
| Target DSH | `0.2.2-rc.1`, `engines.dsh: ">=0.2.2-rc.1 <0.3.0-0"` |
| Market index URL (primary) | `https://qingzhu093.github.io/dsh-greatwall-agent/market/index.json` |
| Market index URL (fallback) | `https://raw.githubusercontent.com/Qingzhu093/dsh-greatwall-agent/main/market/index.json` |
| Community market | <https://dshopen.org/index.json> (index source users add) |

**Layout decision:** the public repository's **root is the package root** (same shape as
`dsh-latex-studio`). That is why `repository.directory` is *omitted* in `market/index.json` —
the format note allows `directory` only for a package inside a subdirectory, and a value like
`"."` or `"/"` is rejected. It is also why GitHub Pages can serve `market/` from the same repo
with no copy step. `npm` still excludes `market/`, `.release/` and `docs/` because `package.json`
`files` is an allow-list.

---

## 0. State at hand-off (2026-11-07, release engineer)

All gates pass on the delivered tree:

| Gate | Result |
| --- | --- |
| `node .release/selftest-index.mjs` | **PASS** — 40/40 cases |
| `node .release/verify-index.mjs` | **PASS** — 0 errors, 1 warning (the expected placeholder warning) |
| `node .release/verify-index.mjs --strict` | **FAIL** as designed — the placeholder is still present (correct before §4) |
| `node tools/verify-core.mjs` | **OK** — 18 core files match `core-manifest.sha256` |
| `pwsh -File .release/verify-pack.ps1` | **PASS** — 107.1 KiB tarball, 33 files, 0 warnings |

One recurring hazard, seen during this work: `greatwall-agent/lib/__pycache__/*.pyc`
(5 files, ~217 KiB) reappeared after a Python run and the pack gate blocked the tarball.
A `files` entry always wins over `.gitignore`, and the kernel recreates those caches every
time it is imported — so run §1 with **`-Clean`** immediately before packing and do not drop
the flag. Removing them by hand right before `npm publish` is the same fix.

---

## 1. Gates — must all pass before anything leaves the machine

```powershell
Set-Location 'D:\Documents\deepseek harness\长城Agent_框架设计\plugins\dsh-greatwall-agent'
node .release/selftest-index.mjs
node .release/verify-index.mjs
pwsh -NoProfile -File .release/verify-pack.ps1 -Clean
node tools/verify-core.mjs
```

Required end state:

```text
selftest-index: PASS
verify-index: PASS — 0 error(s), 1 warning(s)
verify-pack: PASS — …
OK: 18 core files match core-manifest.sha256 (byte-identical Antigravity tree)
```

Notes:

- `-Clean` **deletes** `__pycache__/` and `*.pyc`/`*.pyo` under the package, then packs. Python
  recreates those caches on every import, and `files: ["greatwall-agent"]` **includes** them
  (a `files` entry always wins over `.gitignore`). `-Clean` is the supported fix; run it
  immediately before packing, and never ship a tarball that fails this gate.
- `verify-pack.ps1` runs `npm pack --dry-run --json`; it writes no `.tgz`.
- `npm` lifecycle protection: `package.json` has no `prepublishOnly`/`prepare` scripts, so
  packing does not build anything.

---

## 2. Create the public repository (repo root = package root)

```powershell
$pkg   = 'D:\Documents\deepseek harness\长城Agent_框架设计\plugins\dsh-greatwall-agent'
$stage = Join-Path $env:TEMP 'dsh-greatwall-agent-publish'

Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $stage | Out-Null

# /E copies subdirs incl. hidden files; /XD,/XF drop what must never be committed.
robocopy $pkg $stage /E /XD __pycache__ .git /XF *.pyc *.pyo /NFL /NDL /NJH /NJS /NP
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }

Set-Location $stage
New-Item -ItemType File -Path .nojekyll -Force | Out-Null   # skip Jekyll for the Pages site
git init -b main
git add -A
git status --short
git commit -m "dsh-greatwall-agent 4.2.0"
git branch --show-current        # must print: main
```

Then create and push (the Lead's step):

```powershell
gh repo create Qingzhu093/dsh-greatwall-agent --public `
  --description "Great Wall Agent V4.2 for DeepSeek Harness — unattended AI-for-Science and algorithm-competition campaigns" `
  --source . --remote origin --push
```

Sanity check what was pushed:

```powershell
gh api repos/Qingzhu093/dsh-greatwall-agent --jq '{name,default_branch,visibility,license:.license.spdx_id}'
gh api repos/Qingzhu093/dsh-greatwall-agent/contents/ --jq '.[].name'
```

Expect `default_branch: "main"`, `visibility: "public"`, and top-level entries including
`package.json`, `cordis.patch.yml`, `icon.svg`, `LICENSE`, `market`, `greatwall-agent`, `tools`.

> Alternative preserving design-repo history: `git subtree split --prefix plugins/dsh-greatwall-agent -b publish`
> then `git push origin publish:main`. The staging copy above is deterministic and is what the
> commands below assume.

---

## 3. Publish to npm

From the same staging tree — the exact files that were committed and that `verify-pack.ps1`
approved:

```powershell
Set-Location (Join-Path $env:TEMP 'dsh-greatwall-agent-publish')
npm whoami                                  # expect: ripplesseeing
npm publish --dry-run                       # prints the file list; must match §1
npm publish                                 # add --otp=<code> if the account requires 2FA
```

`publishConfig.access: "public"` is already in `package.json`, so `--access public` is optional.

Verify the registry accepted it:

```powershell
npm view dsh-greatwall-agent version dist-tags --json
npm view dsh-greatwall-agent time --json
```

Expect `version: 4.2.0`, `dist-tags.latest: 4.2.0`, and a `time["4.2.0"]` ISO timestamp.

---

## 4. Finalize the market index timestamp

`market/index.json` ships with the literal token `"__PUBLISH_TIMESTAMP__"` (a real integer is
required by format 1, but the index is committed before the release exists). Substitute the
**registry's own publish time** — never a hand-typed number:

```powershell
Set-Location 'D:\Documents\deepseek harness\长城Agent_框架设计\plugins\dsh-greatwall-agent'
node .release/finalize-index.mjs             # dry run: prints the ISO time and Unix seconds
node .release/finalize-index.mjs --write     # writes market/index.json
node .release/verify-index.mjs --strict      # must print: PASS — 0 error(s), 0 warning(s)
```

Expected dry run, for reference (numbers will differ):

```text
finalize-index: dsh-greatwall-agent@4.2.0 publishTimestamp __PUBLISH_TIMESTAMP__ → 1793012574  (2026-10-26T11:02:54.851Z, from registry https://registry.npmjs.org/dsh-greatwall-agent)
```

Commit and push the finalized index:

```powershell
$pkg   = 'D:\Documents\deepseek harness\长城Agent_框架设计\plugins\dsh-greatwall-agent'
$stage = Join-Path $env:TEMP 'dsh-greatwall-agent-publish'
robocopy (Join-Path $pkg 'market') (Join-Path $stage 'market') /E /NFL /NDL /NJH /NJS /NP
Set-Location $stage
git add market/index.json
git commit -m "market: publishTimestamp for 4.2.0"
git push
```

---

## 5. Enable GitHub Pages for the market

Do this **after** §4: while the placeholder is in the index any user who adds the URL gets a
rejected source (the reader rejects the whole index on that field) instead of a plugin card.

```powershell
gh api --method POST repos/Qingzhu093/dsh-greatwall-agent/pages `
  -f "source[branch]=main" -f "source[path]=/"
```

`-f` with `key[subkey]=value` is the documented `gh api` syntax for nested payload fields
(`gh api --help`), so the request body is exactly
`{"source":{"branch":"main","path":"/"}}`.

- `source.path` must be `/` or `/docs` for a branch source — with the repo root as the package
  root, `/` is the only option, and `market/index.json` is then served one level down.
- If the command returns `HTTP 409` (Pages already exists), use `--method PUT` instead of `POST`.
- The repository must be **public** on a free plan.

Check the site and the first build:

```powershell
gh api repos/Qingzhu093/dsh-greatwall-agent/pages --jq '{html_url, status, build_type, cname}'
gh api repos/Qingzhu093/dsh-greatwall-agent/pages/builds/latest --jq '{status, error: .error.message, duration}'
```

`build_type` should be `legacy` and `status` should become `built`. The first build usually
finishes in 1–3 minutes.

---

## 6. Submit to the Open Plugin Market (community channel)

Requirements from
[`.github/CONTRIBUTING.md`](https://github.com/polang233/dsh-plugin-index/blob/main/.github/CONTRIBUTING.md)
— public npm release; `dsh.bundle.patch` declared **and the patch file inside the published
package**; public repository with a `license` field and a `LICENSE` file; a clear purpose;
compatibility in `engines.dsh`. All satisfied; §1 proves the patch and license actually ship.

The body is prepared in `.release/issue-body.md` (it mirrors the `plugin-add.yml` template):
插件地址 → npm name + repo URL · 简短说明 → one Chinese + one English sentence · 补充信息 →
tested versions, logo URL, security self-check. Screenshots are optional and deliberately omitted.

```powershell
Set-Location 'D:\Documents\deepseek harness\长城Agent_框架设计\plugins\dsh-greatwall-agent'
Get-Content .release/issue-body.md            # read it once before sending

gh issue create --repo polang233/dsh-plugin-index `
  --title "[plugin-add] dsh-greatwall-agent" `
  --body-file .release/issue-body.md
```

Then:

- Listing follows npm's `latest` tag, so `4.2.0` becomes the listed version automatically.
- Reviews are manual; a **new release needs a re-review** — reply in the *same* issue with
  the new version or commit, do not open a new one. Unanswered issues close after 7 days
  (replying or resubmitting later is fine).

---

## 7. Verify what users will actually get

```powershell
$pages = 'https://qingzhu093.github.io/dsh-greatwall-agent/market/index.json'
$raw   = 'https://raw.githubusercontent.com/Qingzhu093/dsh-greatwall-agent/main/market/index.json'

# 1) 200, JSON, and NO redirect (the guide requires a 2xx without redirects)
try {
  $r = Invoke-WebRequest -Uri $pages -UseBasicParsing -MaximumRedirection 0
  "status=$($r.StatusCode) type=$($r.Headers['Content-Type']) bytes=$($r.RawContentLength)"
} catch { "FAILED: $($_.Exception.Message)" }

# 2) validate the bytes that are actually served (strict: no placeholder allowed)
$live = Join-Path $env:TEMP 'live-index.json'
Invoke-WebRequest -Uri $pages -UseBasicParsing -OutFile $live
node .release/verify-index.mjs $live --strict --no-package-check --no-icon-files

# 3) the icon must resolve next to the index
"'icon=' + ((Get-Content $live -Raw | ConvertFrom-Json).plugins[0].icon)"
Invoke-WebRequest -Uri 'https://qingzhu093.github.io/dsh-greatwall-agent/market/icons/dsh-greatwall-agent.svg' -UseBasicParsing | Select-Object StatusCode,RawContentLength

# 4) the fallback URL must serve the same index
(Invoke-WebRequest -Uri $raw -UseBasicParsing).StatusCode
```

Then in DSH itself — this is the only end-to-end proof:

1. **Plugins → More → Custom plugin markets** on.
2. **Discover → Add index source** → paste `$pages`.
3. The **Great Wall Agent V4.2** card shows, **Install** confirms `dsh-greatwall-agent@4.2.0`,
   and after a restart `mcp__greatwall-agent__gw_*` tools and the `greatwall-agent` skill load.

Finally, confirm the community listing once the maintainers merge it:
<https://dshopen.org/plugins/dsh-greatwall-agent/> and search for `greatwall` after adding
<https://dshopen.org/index.json> as a source.

Pages caches for a few minutes; if the site still serves an old index, check
`gh api repos/Qingzhu093/dsh-greatwall-agent/pages/builds/latest` before changing anything.

---

## 8. Sync the design repository

The design repo (`origin` = `https://github.com/Qingzhu093/greatwall-agent.git`) still has the
package as **untracked** (`?? plugins/dsh-greatwall-agent/`); commit it so the source of truth
matches what shipped.

```powershell
Set-Location 'D:\Documents\deepseek harness\长城Agent_框架设计'
git status --porcelain plugins/dsh-greatwall-agent | Select-Object -First 20
git add plugins/dsh-greatwall-agent
git commit -m "release: dsh-greatwall-agent 4.2.0 — market index, release gates, release tooling"
git push origin main
```

`.gitignore` already excludes `__pycache__/`, `*.pyc` and `.release/tmp/`, so caches stay out.
`market/` and `.release/` **are** committed on purpose — they are the market source and the
repeatable release gates.

---

## 9. Every later release

1. Bump `package.json` `version` (keep `engines.dsh` unchanged unless the DSH range changes).
2. Add the new version object to `plugins[0].versions` in `market/index.json`, keeping the old
   entries; point `dist-tags.latest` at the new version.
3. §1 gates → §2 copy to the staging tree (`git pull` there first) → commit → push.
4. §3 `npm publish` → §4 finalize the new version's timestamp (`finalize-index.mjs` refuses to
   guess: it reads that version's time from the registry) → `--strict` verify → push.
5. Reply in the Open Plugin Market issue for a re-review — the listing follows `latest`, the
   review does not.
6. §7 verify, §8 sync the design repo.

---

## 10. Rollback

| Situation | Action |
| --- | --- |
| Bad code published | Publish a fixed **patch version** (preferred). `npm unpublish dsh-greatwall-agent@4.2.0 --force` only works within 72 h and breaks anyone who pinned it. |
| Bad/wrong index | Revert `market/index.json`, push, wait for the Pages rebuild (~2 min). Never leave a placeholder or a `publishTimestamp` copied from the wrong version. |
| Market must go dark | `gh api --method DELETE repos/Qingzhu093/dsh-greatwall-agent/pages` (disables the site; the repo and npm package are unaffected). |
| Listing must be withdrawn | Open the `plugin-remove.yml` issue as the package owner (same account that published to npm). |

---

## 11. What the release engineer verified (and did not)

Verified by execution: index format rules against the pin to `dsh-v0.2.2-rc.1`, 40 negative
self-test cases, the pack listing (33 files) including `core-manifest.sha256` coverage and the
`node tools/verify-core.mjs` hash match, the registry timestamp conversion (cross-checked
against `npm view` for a published package), and the community-market requirements against its
CONTRIBUTING, issue template and live `index.json`.

**Not** executed, by instruction: `npm publish`, `git push`, `gh repo create`,
`gh issue create`, Pages enablement.

Unverified caveats: the exact DSH CLI for a local install smoke test (use the Discover flow in
§7 instead); GitHub Pages build time and propagation for a brand-new repository.
