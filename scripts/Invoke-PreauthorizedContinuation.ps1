[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [switch]$Apply,
    [string]$Actor = "autopilot:preauthorized-continuation"
)

# This is the canonical attended-to-autonomous handoff.  An owner grants the
# routine/reversible continuation in conversation or by launching this script;
# a later agent invocation must re-observe live control-plane truth instead of
# replaying an old branch, node, credential, or command.  The only mutating
# capability is Autopilot's already-gated dispatcher release (`-Apply`).
#
# It deliberately does not read credentials, set environment variables, invoke
# a shell, weaken TLS or execution policy, push a ref, merge, deploy, or invent
# an external root.  Those boundaries remain in their own capability paths.

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Join-Path $PSScriptRoot ".."
}

if ($Actor -notmatch '^[A-Za-z0-9:_-]+$') {
    throw "Actor must be a non-empty portable identifier."
}

$root = (Resolve-Path -LiteralPath $RepoRoot).Path
$cli = Join-Path $root ".autopilot\bin\autopilot.py"
if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) {
    throw "Canonical Autopilot CLI is missing: $cli"
}

$insideRepository = (& git -C $root rev-parse --is-inside-work-tree 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $insideRepository -ne "true") {
    throw "Continuation root is not a Git repository: $root"
}

$python = (Get-Command python -ErrorAction Stop).Source
$request = "Continue the existing authorized routine and reversible Hive Mind work. Reconcile live state, use only current releases, preserve blockers and dissent."
$arguments = @(
    $cli,
    "--repo-root", $root,
    "orchestrate",
    "--actor", $Actor,
    "--request", $request,
    "--json"
)
if ($Apply) {
    $arguments += "--apply"
}

$output = & $python @arguments 2>&1
$exitCode = $LASTEXITCODE
$output | ForEach-Object { Write-Host $_ }
if ($exitCode -ne 0) {
    throw "Preauthorized continuation failed with exit code $exitCode. Preserve its typed blocker; do not bypass a control."
}

if ($Apply) {
    Write-Host "CONTINUATION APPLIED: only a live, safe dispatcher release could have been published."
} else {
    Write-Host "CONTINUATION INSPECTED: no dispatcher release was requested. Use -Apply only under an explicit continuation directive."
}
