[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
    [string]$Node = "ARCH-100",
    [string]$Owner = "codex:arch-100"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $RepoRoot

function Invoke-Checked {
    param(
        [string]$Label,
        [string]$File,
        [string[]]$Arguments
    )
    Write-Host "== $Label"
    $output = & $File @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) {
        throw "$Label failed with exit code $exitCode. Preserve the output as a blocker packet; do not bypass security controls."
    }
    return (($output -join "`n"))
}

$controlPath = Join-Path $RepoRoot ".autopilot\control-plane.json"
$control = Get-Content -LiteralPath $controlPath -Raw | ConvertFrom-Json
$targetBranch = [string]$control.target.branch
$finalBranch = [string]$control.final_integration_branch
if ([string]::IsNullOrWhiteSpace($targetBranch) -or $targetBranch -eq $finalBranch -or $targetBranch -eq "main") {
    throw "Unsafe target branch configuration: '$targetBranch'. Fix the singleton release target before retrying."
}

$headBranch = (git branch --show-current).Trim()
if ($headBranch -ne $targetBranch) {
    throw "Wrong checkout '$headBranch'. Check out the singleton release branch '$targetBranch' before retrying."
}

Invoke-Checked "fetch current singleton release" "git" @("fetch", "origin", "--prune") | Out-Null
$liveTarget = (git rev-parse "refs/remotes/origin/$targetBranch").Trim()
if ($LASTEXITCODE -ne 0 -or $liveTarget -notmatch '^[0-9a-f]{40}$') {
    throw "Cannot resolve live singleton target. Fix Git remote access before retrying."
}

# This is the independent secure transport check. No SSL, Schannel, proxy, or
# certificate-verification bypass is permitted here.
Invoke-Checked "verified remote branch inspection" "git" @("ls-remote", "--heads", "origin", "refs/heads/$targetBranch") | Out-Null

$snapshotPath = Join-Path $RepoRoot ".autopilot\state\github-state.json"
if (-not (Test-Path -LiteralPath $snapshotPath)) {
    throw "GitHub snapshot is missing. Install a current authenticated snapshot, then rerun this script."
}
$snapshot = Get-Content -LiteralPath $snapshotPath -Raw | ConvertFrom-Json
if ([string]$snapshot.target_sha -ne $liveTarget) {
    throw "GitHub snapshot target '$($snapshot.target_sha)' is stale; install a snapshot for '$liveTarget' before retrying."
}

$python = (Get-Command python).Source
$cli = Join-Path $RepoRoot ".autopilot\bin\autopilot.py"
Invoke-Checked "install current snapshot" $python @($cli, "--repo-root", $RepoRoot, "install-github-snapshot", $snapshotPath) | Out-Null
Invoke-Checked "reconcile current target" $python @($cli, "--repo-root", $RepoRoot, "reconcile", "--target-sha", $liveTarget, "--actor", "dispatcher:singleton-master-script", "--reason", "ordered singleton recovery") | Out-Null
Invoke-Checked "doctor" $python @($cli, "--repo-root", $RepoRoot, "doctor", "--skip-controller-tests") | Out-Null

$statusText = Invoke-Checked "status" $python @($cli, "--repo-root", $RepoRoot, "status", "--json")
$status = $statusText | ConvertFrom-Json
$eligible = @($status.eligible)
if ($eligible -notcontains $Node) {
    throw "Node '$Node' is not eligible after reconciliation. Preserve status output and follow the reported blocker."
}

$dispatchText = Invoke-Checked "dispatch explicit release" $python @($cli, "--repo-root", $RepoRoot, "dispatch", "--actor", "dispatcher:singleton-master-script", "--node", $Node, "--json")
$dispatch = $dispatchText | ConvertFrom-Json
if ([string]$dispatch.directive -ne "START NOW" -or @($dispatch.released_wave) -notcontains $Node) {
    throw "Dispatcher did not issue START NOW for '$Node'. Do not attempt claim-first recovery."
}

Invoke-Checked "claim remote node branch" $python @($cli, "--repo-root", $RepoRoot, "claim", $Node, "--owner", $Owner, "--publish-remote") | Out-Null
Write-Host "RECOVERY COMPLETE: $Node claimed on $targetBranch at $liveTarget"
