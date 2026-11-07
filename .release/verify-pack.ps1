#Requires -Version 7.0
<#
.SYNOPSIS
    Verify the npm tarball for dsh-greatwall-agent before `npm publish`.

.DESCRIPTION
    Runs `npm pack --dry-run --json` in the package directory (read-only: --dry-run
    never writes a .tgz) and then asserts, against the reported file list:

      1. every file the plugin needs at runtime or for a usable npm page is present
         (paths taken from lib/index.js, lib/skillpack.js, package.json `main`/`files`,
         and the npm package-page conventions);
      2. no junk ships: Python caches, OS/editor noise, VCS directories, repo-only
         trees (market/, .release/, docs/), or stray archives.

    The listing is authoritative because npm decides, not us: entries in `files`
    are always packed and `.gitignore`/`.npmignore` cannot remove them — which is
    exactly how `greatwall-agent/lib/__pycache__` used to ride along in
    `files: ["greatwall-agent"]`.

.PARAMETER PackageDir
    Package root. Defaults to the parent directory of this script (.release/..).

.PARAMETER Clean
    MUTATES THE TREE: delete __pycache__/ and *.pyc/*.pyo under the package before
    packing. This is the documented fix for re-created Python caches right before a
    release; it never touches anything outside the package directory.

.PARAMETER FailOnWarn
    Also fail on warnings (e.g. an unexpected but harmless extra file).

.PARAMETER SkipCoreVerify
    Do not run `node tools/verify-core.mjs` (the sha256 proof that the shipped
    greatwall-agent/ tree is byte-identical to the original Antigravity core).

.EXAMPLE
    pwsh -NoProfile -File .release/verify-pack.ps1
    pwsh -NoProfile -File .release/verify-pack.ps1 -Clean
#>
[CmdletBinding()]
param(
    [string] $PackageDir = (Split-Path -Parent $PSScriptRoot),
    [switch] $Clean,
    [switch] $FailOnWarn,
    [switch] $SkipCoreVerify
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$failures = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()
$notes = [System.Collections.Generic.List[string]]::new()

function Add-Failure([string] $message) { $script:failures.Add($message) }
function Add-Warning([string] $message) { $script:warnings.Add($message) }

function Format-Bytes([double] $bytes) {
    if ($bytes -ge 1MB) { return ('{0:N1} MiB' -f ($bytes / 1MB)) }
    if ($bytes -ge 1KB) { return ('{0:N1} KiB' -f ($bytes / 1KB)) }
    return ('{0:N0} B' -f $bytes)
}

# ---------------------------------------------------------------------------
# 0. Preconditions
# ---------------------------------------------------------------------------
$PackageDir = (Resolve-Path -LiteralPath $PackageDir).Path
$manifestPath = Join-Path $PackageDir 'package.json'
if (-not (Test-Path -LiteralPath $manifestPath)) {
    Write-Host "verify-pack: FAIL — no package.json under $PackageDir"
    exit 1
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host 'verify-pack: FAIL — npm is not on PATH'
    exit 1
}

# ---------------------------------------------------------------------------
# 1. Optional: clean Python caches (the documented junk-prevention step)
# ---------------------------------------------------------------------------
if ($Clean) {
    $removed = 0
    Get-ChildItem -LiteralPath $PackageDir -Recurse -Directory -Force -Filter '__pycache__' -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName.StartsWith($PackageDir, [System.StringComparison]::OrdinalIgnoreCase) } |
        ForEach-Object {
            Write-Host "  clean: $([System.IO.Path]::GetRelativePath($PackageDir, $_.FullName))"
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
            $script:removed++
        }
    Get-ChildItem -LiteralPath $PackageDir -Recurse -File -Force -Include '*.pyc', '*.pyo' -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName.StartsWith($PackageDir, [System.StringComparison]::OrdinalIgnoreCase) } |
        ForEach-Object {
            Write-Host "  clean: $([System.IO.Path]::GetRelativePath($PackageDir, $_.FullName))"
            Remove-Item -LiteralPath $_.FullName -Force
        }
    Write-Host "  clean: removed $removed __pycache__ director$(if ($removed -eq 1) { 'y' } else { 'ies' })"
}

# ---------------------------------------------------------------------------
# 2. Manifest sanity (what the market index and DSH installation rely on)
# ---------------------------------------------------------------------------
if ($manifest.name -ne 'dsh-greatwall-agent') {
    Add-Warning "package.json name is '$($manifest.name)', not 'dsh-greatwall-agent' (the market index lists that name)"
}
if (-not $manifest.engines.dsh) {
    Add-Failure 'package.json has no engines.dsh; the market index copies it and DSH rechecks it at install time'
} else {
    $notes.Add("engines.dsh = $($manifest.engines.dsh)")
}
if (-not $manifest.dsh.bundle.patch) {
    Add-Failure 'package.json has no dsh.bundle.patch; installation refuses a package without a bundle patch'
} else {
    $patch = Join-Path $PackageDir ($manifest.dsh.bundle.patch -replace '^\./', '')
    if (-not (Test-Path -LiteralPath $patch)) {
        Add-Failure "dsh.bundle.patch points at $($manifest.dsh.bundle.patch), which does not exist"
    } else {
        $notes.Add("dsh.bundle.patch = $($manifest.dsh.bundle.patch)")
    }
}
if (-not $manifest.main) { Add-Failure 'package.json has no main entry' }

# ---------------------------------------------------------------------------
# 3. npm pack --dry-run --json  (authoritative file list)
# ---------------------------------------------------------------------------
$stdErrFile = Join-Path ([System.IO.Path]::GetTempPath()) "verify-pack-$PID.stderr"
Push-Location -LiteralPath $PackageDir
try {
    $stdout = & npm pack --dry-run --json 2> $stdErrFile
    $npmExit = $LASTEXITCODE
} finally {
    Pop-Location
}
$stdErr = if (Test-Path -LiteralPath $stdErrFile) { Get-Content -LiteralPath $stdErrFile -Raw } else { '' }
if (Test-Path -LiteralPath $stdErrFile) { Remove-Item -LiteralPath $stdErrFile -Force }

if ($npmExit -ne 0) {
    Write-Host "verify-pack: FAIL — 'npm pack --dry-run --json' exited $npmExit"
    if ($stdErr) { Write-Host $stdErr.Trim() }
    exit 1
}

try {
    $pack = ($stdout -join "`n") | ConvertFrom-Json
} catch {
    Write-Host "verify-pack: FAIL — could not parse npm pack JSON: $($_.Exception.Message)"
    Write-Host (($stdout -join "`n").Trim())
    exit 1
}
if ($pack -is [array]) { $pack = $pack[0] }

$paths = @($pack.files | ForEach-Object { $_.path })
$pathSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
foreach ($p in $paths) { [void]$pathSet.Add($p) }

# ---------------------------------------------------------------------------
# 4. Required content
# ---------------------------------------------------------------------------
# Exact paths whose loss breaks the plugin at runtime, the npm page, or licensing.
$requiredExact = [ordered]@{
    'package.json'                                       = 'npm manifest'
    'cordis.patch.yml'                                   = 'bundle patch'
    'icon.svg'                                           = 'package icon (package.json icon)'
    'LICENSE'                                            = 'license (also a listing requirement of the Open Plugin Market)'
    'README.md'                                          = 'readme (declared in package.json files[])'
    'README.en.md'                                       = 'English readme (declared in package.json files[])'
    'core-manifest.sha256'                               = 'sha256 manifest of the byte-identical core tree'
    'lib/index.js'                                       = 'host entry (package.json main)'
    'locale/en.json'                                     = 'locale baseline'
    'tools/verify-core.mjs'                              = 'provenance checker (package.json script verify:core)'
    'tools/make-core-manifest.mjs'                       = 'manifest generator (package.json script manifest:core)'
    'greatwall-agent/bin/gw_mcp_server.py'               = 'MCP server (lib/index.js SERVER_SCRIPT)'
    'greatwall-agent/skills/greatwall-campaign/SKILL.md' = 'skill pack (lib/skillpack.js reads <dir>/<name>/SKILL.md)'
}

# Patterns with a minimum count, for "all of a directory" requirements.
$requiredPatterns = @(
    @{ Pattern = 'lib/*.js'; Label = 'host JS modules'; Min = 1 }
    @{ Pattern = 'locale/*.json'; Label = 'locale files'; Min = 1 }
    @{ Pattern = 'greatwall-agent/lib/*.py'; Label = 'Python kernel modules'; Min = 1 }
    @{ Pattern = 'greatwall-agent/skills/**'; Label = 'skills tree'; Min = 1 }
)

# Paths that mean the package is not publishable, even when npm would happily pack them.
$forbiddenPatterns = @(
    @{ Pattern = '*/__pycache__/*'; Label = 'Python bytecode cache directory (files[] whitelist wins over .gitignore)' }
    @{ Pattern = '*.pyc'; Label = 'Python bytecode' }
    @{ Pattern = '*.pyo'; Label = 'Python bytecode' }
    @{ Pattern = '*/.pytest_cache/*'; Label = 'pytest cache' }
    @{ Pattern = '*.DS_Store'; Label = 'macOS metadata' }
    @{ Pattern = '*/Thumbs.db'; Label = 'Windows metadata' }
    @{ Pattern = '*/desktop.ini'; Label = 'Windows metadata' }
    @{ Pattern = 'node_modules/*'; Label = 'installed dependencies' }
    @{ Pattern = '*/.git/*'; Label = 'Git internals' }
    @{ Pattern = '*.tgz'; Label = 'pre-built tarball' }
    @{ Pattern = 'market/*'; Label = 'repo-only market source (served by GitHub Pages, not packaged)' }
    @{ Pattern = '.release/*'; Label = 'repo-only release tooling' }
    @{ Pattern = 'docs/*'; Label = 'repo-only design docs' }
    @{ Pattern = 'RELEASE.md'; Label = 'repo-only release checklist' }
    @{ Pattern = 'package-lock.json'; Label = 'lockfile (npm excludes it anyway)' }
)

Write-Host ("verify-pack: {0}@{1}" -f $pack.name, $pack.version)
Write-Host ("  tarball {0}  →  {1} unpacked  ({2} files)" -f (Format-Bytes $pack.size), (Format-Bytes $pack.unpackedSize), $pack.entryCount)

Write-Host ''
Write-Host 'REQUIRED'
foreach ($relative in $requiredExact.Keys) {
    if ($pathSet.Contains($relative)) {
        Write-Host ("  ok    {0}  ({1})" -f $relative, $requiredExact[$relative])
    } else {
        Write-Host ("  FAIL  {0}  — missing ({1})" -f $relative, $requiredExact[$relative])
        Add-Failure "missing required file: $relative ($($requiredExact[$relative]))"
    }
}
foreach ($entry in $requiredPatterns) {
    $hits = @($paths | Where-Object { $_ -like $entry.Pattern })
    if ($hits.Count -ge $entry.Min) {
        Write-Host ("  ok    {0}  — {1} file(s), e.g. {2}" -f $entry.Pattern, $hits.Count, $hits[0])
    } else {
        Write-Host ("  FAIL  {0}  — expected at least {1} {2}, found {3}" -f $entry.Pattern, $entry.Min, $entry.Label, $hits.Count)
        Add-Failure "missing required content: $($entry.Pattern) ($($entry.Label)); expected >= $($entry.Min), found $($hits.Count)"
    }
}

# ---------------------------------------------------------------------------
# 4b. Provenance: core-manifest.sha256 must describe exactly what ships
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host 'CORE PROVENANCE'
$manifestFile = Join-Path $PackageDir 'core-manifest.sha256'
if (-not (Test-Path -LiteralPath $manifestFile)) {
    Write-Host '  FAIL  core-manifest.sha256 — missing'
    Add-Failure 'missing core-manifest.sha256; greatwall-agent/ is shipped byte-identical and the manifest is the proof'
} else {
    $manifestLines = @(Get-Content -LiteralPath $manifestFile | Where-Object { $_.Trim().Length -gt 0 })
    $malformed = @($manifestLines | Where-Object { $_ -notmatch '^[0-9a-f]{64} {2}.+$' })
    if ($malformed.Count -gt 0) {
        Write-Host ("  FAIL  {0} malformed manifest line(s); expected '<64 hex>  <path>'" -f $malformed.Count)
        Add-Failure "core-manifest.sha256 has $($malformed.Count) malformed line(s)"
    }
    $manifestPaths = @($manifestLines | ForEach-Object { ($_ -split ' {2}', 2)[1] })
    $absent = @($manifestPaths | Where-Object { -not $pathSet.Contains("greatwall-agent/$_") })
    if ($absent.Count -gt 0) {
        Write-Host ("  FAIL  {0} manifest path(s) would not ship, e.g. {1}" -f $absent.Count, $absent[0])
        Add-Failure "core-manifest.sha256 names $($absent.Count) file(s) absent from the tarball: $($absent -join ', ')"
    } else {
        Write-Host ("  ok    all {0} manifest path(s) ship as greatwall-agent/<path>" -f $manifestPaths.Count)
    }

    if ($SkipCoreVerify) {
        Write-Host '  ..    node tools/verify-core.mjs skipped (-SkipCoreVerify)'
    } else {
        Push-Location -LiteralPath $PackageDir
        try {
            $coreOutput = & node tools/verify-core.mjs 2>&1
            $coreExit = $LASTEXITCODE
        } finally {
            Pop-Location
        }
        if ($coreExit -eq 0) {
            Write-Host ("  ok    node tools/verify-core.mjs — {0}" -f @($coreOutput)[-1])
        } else {
            Write-Host '  FAIL  node tools/verify-core.mjs reported drift in greatwall-agent/'
            foreach ($line in @($coreOutput | Select-Object -Last 12)) { Write-Host "        $line" }
            Add-Failure 'greatwall-agent/ no longer matches core-manifest.sha256 (only regenerate with tools/make-core-manifest.mjs when the core change is intended)'
        }
    }
}

# ---------------------------------------------------------------------------
# 5. Junk / should-not-ship content
# ---------------------------------------------------------------------------
Write-Host ''
Write-Host 'SHOULD NOT SHIP'
$junk = 0
foreach ($entry in $forbiddenPatterns) {
    $hits = @($paths | Where-Object { $_ -like $entry.Pattern })
    if ($hits.Count -eq 0) { continue }
    $junk++
    foreach ($hit in $hits) {
        Write-Host ("  FAIL  {0}  — {1}" -f $hit, $entry.Label)
    }
    Add-Failure "packed junk: $($hits.Count) × $($entry.Pattern) ($($entry.Label))"
}
if ($junk -eq 0) { Write-Host '  ok    no junk patterns matched' }

# ---------------------------------------------------------------------------
# 6. Extra signal: largest files, unexpected-but-harmless extras
# ---------------------------------------------------------------------------
$total = $pack.unpackedSize
$sorted = @($pack.files | Sort-Object -Property size -Descending)
Write-Host ''
Write-Host ('LARGEST FILES (total {0})' -f (Format-Bytes $total))
foreach ($file in ($sorted | Select-Object -First 5)) {
    Write-Host ("  {0,10}  {1}" -f (Format-Bytes $file.size), $file.path)
}

if ($total -gt 5MB) {
    Add-Warning ("unpacked size {0} exceeds 5 MiB; npm install and every update download this" -f (Format-Bytes $total))
}
$unexpected = @($paths | Where-Object {
        $_ -notin $requiredExact.Keys -and
        $_ -notlike 'greatwall-agent/*' -and
        $_ -notlike 'lib/*' -and
        $_ -notlike 'locale/*' -and
        $_ -notlike 'tools/*' -and
        $_ -ne 'core-manifest.sha256'
    })
foreach ($p in $unexpected) {
    Add-Warning "unexpected file in tarball: $p"
}

# ---------------------------------------------------------------------------
# 7. Summary
# ---------------------------------------------------------------------------
if ($warnings.Count -gt 0) {
    Write-Host ''
    Write-Host 'WARNINGS'
    foreach ($w in $warnings) { Write-Host "  WARN  $w" }
}

if ($failures.Count -gt 0) {
    Write-Host ''
    Write-Host "BLOCKERS ($($failures.Count))"
    $i = 0
    foreach ($f in $failures) { $i++; Write-Host "  $i. $f" }
    Write-Host ''
    Write-Host 'REMEDIATION'
    Write-Host '  Python caches (re-created every time the kernel is imported):'
    Write-Host '    pwsh -NoProfile -File .release/verify-pack.ps1 -Clean'
    Write-Host '  or manually, before packing:'
    Write-Host ("    Get-ChildItem -LiteralPath '{0}' -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force" -f $PackageDir)
    Write-Host '  Missing README.md / README.en.md are declared in package.json files[] but not written yet.'
    Write-Host ''
    Write-Host "verify-pack: FAIL — $($failures.Count) blocker(s), $($warnings.Count) warning(s)"
    exit 1
}

if ($FailOnWarn -and $warnings.Count -gt 0) {
    Write-Host ''
    Write-Host "verify-pack: FAIL — $($warnings.Count) warning(s) and -FailOnWarn is set"
    exit 1
}

Write-Host ''
Write-Host "verify-pack: PASS — $(Format-Bytes $pack.size) tarball, $($pack.entryCount) files, $($warnings.Count) warning(s)"
exit 0
