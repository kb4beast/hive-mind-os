[CmdletBinding()]
param(
    [string]$Repository = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "HiveMindOS\whole-os-codex-host"),
    [string]$TenantId = "local-operator",
    [string]$RepositoryId = "hive-mind-os",
    [ValidateRange(60, 3600)]
    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path -LiteralPath $Repository).Path
$gitRoot = (& git -C $repositoryRoot rev-parse --show-toplevel 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or (Resolve-Path -LiteralPath $gitRoot).Path -ne $repositoryRoot) {
    throw "Trusted Whole-OS host requires the exact root of a Git checkout: $repositoryRoot"
}
if (-not $StateRoot) {
    throw "Trusted Whole-OS host state root is required."
}
$resolvedStateRoot = [System.IO.Path]::GetFullPath($StateRoot)
$sourceRoot = Join-Path $repositoryRoot "src"
$python = (Get-Command python -ErrorAction Stop).Source
$priorPythonPath = $env:PYTHONPATH
$priorBytecode = $env:PYTHONDONTWRITEBYTECODE
try {
    $env:PYTHONPATH = $sourceRoot
    $env:PYTHONDONTWRITEBYTECODE = "1"
    & $python -m hive_mind_os.whole_os_codex_host `
        --repository $repositoryRoot `
        --state-root $resolvedStateRoot `
        --tenant-id $TenantId `
        --repository-id $RepositoryId `
        --timeout-seconds $TimeoutSeconds
    exit $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $priorPythonPath
    $env:PYTHONDONTWRITEBYTECODE = $priorBytecode
}
