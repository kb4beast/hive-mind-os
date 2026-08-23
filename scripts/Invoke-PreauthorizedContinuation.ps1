[CmdletBinding()]
param(
    [switch]$Apply
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

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$cli = Join-Path $root ".autopilot\bin\autopilot.py"
if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) {
    throw "Canonical Autopilot CLI is missing: $cli"
}

$repositoryRoot = (& git -C $root rev-parse --show-toplevel 2>$null).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Continuation root is not a Git repository: $root"
}
$repositoryRoot = (Resolve-Path -LiteralPath $repositoryRoot).Path
if ($repositoryRoot -ne $root) {
    throw "Continuation root is not this launcher's Git repository: $root"
}

# The controller is part of the authorized repository scope.  Refuse to execute a
# locally edited controller even if a caller manages to launch this file from an
# untrusted checkout; only the committed controller at this repository root runs.
& git -C $root diff --quiet -- ".autopilot/bin/autopilot.py"
if ($LASTEXITCODE -ne 0) {
    throw "Canonical Autopilot controller is modified; commit or revert it before continuation."
}
& git -C $root diff --cached --quiet -- ".autopilot/bin/autopilot.py"
if ($LASTEXITCODE -ne 0) {
    throw "Canonical Autopilot controller is staged but uncommitted; seal it before continuation."
}
$controllerDigest = (& git -C $root rev-parse "HEAD:.autopilot/bin/autopilot.py" 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $controllerDigest -notmatch '^[0-9a-f]{40,64}$') {
    throw "Canonical Autopilot controller is not a committed Git blob."
}

$python = (Get-Command python -ErrorAction Stop).Source
$actor = "autopilot:preauthorized-continuation"
$request = "Continue the existing authorized routine and reversible Hive Mind work. Reconcile live state, use only current releases, preserve blockers and dissent."
$arguments = @(
    $cli,
    "--repo-root", $root,
    "orchestrate",
    "--actor", $actor,
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

try {
    $contract = ($output | Out-String | ConvertFrom-Json -ErrorAction Stop)
} catch {
    throw "Preauthorized continuation returned no valid structured contract. Preserve the output; do not infer success."
}

if ($Apply) {
    if ($contract.release_publication.published -ne $true) {
        $issues = @($contract.dispatch_release.issues | ForEach-Object { [string]$_ })
        $detail = if ($issues.Count -gt 0) { $issues -join "; " } else { "no eligible safe dispatcher release" }
        Write-Host "CONTINUATION WITHHELD: $detail"
        exit 3
    }
    Write-Host "CONTINUATION APPLIED: live dispatcher release published from committed controller $controllerDigest."
} else {
    Write-Host "CONTINUATION INSPECTED: no dispatcher release was requested. Use -Apply only under an explicit continuation directive. Controller: $controllerDigest"
}
