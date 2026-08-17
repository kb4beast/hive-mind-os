[CmdletBinding()]
param(
    [string]$Repository = (Resolve-Path (Join-Path $PSScriptRoot "..")),
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA "HiveMindOS\runtimes"),
    [switch]$Recreate
)

# A machine has exactly one user-level editable install of hive-mind-os, so the
# last `pip install -e .` anywhere silently owns `import hive_mind_os` and the
# `hive-mind` command for every project on the account. That is invisible: the
# code you edit is not the code that runs, and a stale install can drop modules
# an up-to-date checkout depends on.
#
# This provisions a virtual environment owned by ONE checkout, so several
# checkouts -- different projects, or two versions under comparison -- can run at
# the same time without shadowing each other.
#
# The environment is created OUTSIDE the repository. Repository tooling
# enumerates and digests the working tree, and a checkout carrying thousands of
# interpreter files would change what those observations mean.

$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path -LiteralPath $Repository).Path
$sourceRoot = Join-Path $repositoryRoot "src"
if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot "hive_mind_os"))) {
    throw "$repositoryRoot is not a hive-mind-os checkout: src/hive_mind_os is absent."
}

# Name the environment after the checkout it serves, so two worktrees of one
# repository never collide and the mapping stays legible in the filesystem.
$identity = [System.Security.Cryptography.SHA256]::HashData(
    [System.Text.Encoding]::UTF8.GetBytes($repositoryRoot.ToLowerInvariant())
)
$shortId = -join ($identity[0..5] | ForEach-Object { $_.ToString("x2") })
$leafName = (Split-Path -Leaf $repositoryRoot)
$venvRoot = Join-Path $RuntimeRoot "$leafName-$shortId"

if ($Recreate -and (Test-Path -LiteralPath $venvRoot)) {
    Write-Host "== removing existing environment $venvRoot"
    Remove-Item -LiteralPath $venvRoot -Recurse -Force
}

if (-not (Test-Path -LiteralPath $venvRoot)) {
    Write-Host "== creating $venvRoot"
    New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
    & python -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) { throw "virtual environment creation failed with exit code $LASTEXITCODE." }
}

$venvPython = Join-Path $venvRoot "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "expected interpreter is missing: $venvPython"
}

Write-Host "== installing $repositoryRoot into its own environment"
& $venvPython -m pip install --no-deps --quiet -e $repositoryRoot
if ($LASTEXITCODE -ne 0) { throw "editable install failed with exit code $LASTEXITCODE." }

# Prove the isolation rather than assume it: the environment must import this
# checkout, not whichever one the user-level install happens to point at.
$resolved = & $venvPython -c "import hive_mind_os, pathlib; print(pathlib.Path(hive_mind_os.__file__).resolve())"
if ($LASTEXITCODE -ne 0) { throw "the installed package could not be imported." }

$expected = (Join-Path $sourceRoot "hive_mind_os\__init__.py")
if ($resolved.Trim() -ne $expected) {
    throw "environment resolves hive_mind_os to $resolved, expected $expected."
}

Write-Host ""
Write-Host "Isolated runtime ready."
Write-Host "  repository : $repositoryRoot"
Write-Host "  interpreter: $venvPython"
Write-Host "  command    : $(Join-Path $venvRoot 'Scripts\hive-mind.exe')"
Write-Host ""
Write-Host "Run this checkout without disturbing any other project:"
Write-Host "  & '$venvPython' -m hive_mind_os.cli autopilot inspect --repository <target>"
Write-Host ""
Write-Host "Or activate it for the current shell only:"
Write-Host "  . '$(Join-Path $venvRoot 'Scripts\Activate.ps1')'"
