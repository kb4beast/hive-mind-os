[CmdletBinding()]
param(
    [string]$Repository = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "HiveMindOS\whole-os-pipeline"),
    [string]$Model = "gpt-5.6-sol",
    [ValidateSet("low", "medium", "high", "xhigh", "max", "ultra")]
    [string]$ReasoningEffort = "high",
    [ValidateSet("bounded-operational-production-pilot", "full-autonomy-or-superiority")]
    [string]$ClaimScope = "full-autonomy-or-superiority",
    [ValidateRange(60, 86400)]
    [int]$DefaultRetrySeconds = 900,
    [switch]$Once,
    [switch]$Background
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path -LiteralPath $Repository).Path
New-Item -ItemType Directory -Force -Path $StateRoot | Out-Null

if ($Background) {
    $processReceipt = Join-Path $StateRoot "pipeline-process.json"
    if (Test-Path -LiteralPath $processReceipt -PathType Leaf) {
        $priorProcess = $null
        try {
            $prior = Get-Content -LiteralPath $processReceipt -Raw | ConvertFrom-Json
            $priorProcess = Get-Process -Id ([int]$prior.process_id) -ErrorAction SilentlyContinue
        } catch {
            Write-Verbose "Prior process receipt is stale or unreadable; starting a successor."
        }
        if ($null -ne $priorProcess) {
            $priorScope = if ($prior.PSObject.Properties.Name -contains "claim_scope") {
                [string]$prior.claim_scope
            } else {
                "full-autonomy-or-superiority"
            }
            if ($priorScope -ne $ClaimScope) {
                throw "Running pipeline belongs to claim scope $priorScope, not $ClaimScope."
            }
            Write-Host "WHOLE-OS PIPELINE ALREADY RUNNING: PID $($prior.process_id)"
            exit 0
        }
    }
    foreach ($value in @($PSCommandPath, $repositoryRoot, $StateRoot, $Model, $ReasoningEffort, $ClaimScope)) {
        if ($value.Contains('"')) { throw "Background launcher arguments cannot contain quotes." }
    }
    $stdout = Join-Path $StateRoot "pipeline.stdout.log"
    $stderr = Join-Path $StateRoot "pipeline.stderr.log"
    $powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
    $nativeArguments = '-NoProfile -File "{0}" -Repository "{1}" -StateRoot "{2}" -Model "{3}" -ReasoningEffort "{4}" -ClaimScope "{5}" -DefaultRetrySeconds {6}' -f $PSCommandPath, $repositoryRoot, $StateRoot, $Model, $ReasoningEffort, $ClaimScope, $DefaultRetrySeconds
    if ($Once) { $nativeArguments += " -Once" }
    $process = Start-Process -FilePath $powershell -ArgumentList $nativeArguments -WorkingDirectory $repositoryRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    [ordered]@{
        schema_version = 2
        claim_scope = $ClaimScope
        process_id = $process.Id
        started_at = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        repository = $repositoryRoot
        state_root = $StateRoot
        stdout = $stdout
        stderr = $stderr
    } | ConvertTo-Json | Set-Content -LiteralPath $processReceipt -Encoding UTF8
    Write-Host "WHOLE-OS PIPELINE STARTED: PID $($process.Id)"
    Write-Host "WHOLE-OS PIPELINE STATE: $StateRoot"
    exit 0
}

$stages = if ($ClaimScope -eq "bounded-operational-production-pilot") {
    @(
        [ordered]@{ id = "host-bootstrap"; script = "Invoke-WholeOSHostBootstrap.ps1" },
        [ordered]@{ id = "n32-external-pilot"; script = "Invoke-WholeOSN32ExternalPilot.ps1" },
        [ordered]@{ id = "n33-closeout"; script = "Invoke-WholeOSN33Closeout.ps1" }
    )
} else {
    @(
        [ordered]@{ id = "host-bootstrap"; script = "Invoke-WholeOSHostBootstrap.ps1" },
        [ordered]@{ id = "n30-tournament"; script = "Invoke-WholeOSN30Tournament.ps1" },
        [ordered]@{ id = "n31-self-pilot"; script = "Invoke-WholeOSN31SelfPilot.ps1" },
        [ordered]@{ id = "n32-external-pilot"; script = "Invoke-WholeOSN32ExternalPilot.ps1" },
        [ordered]@{ id = "n33-closeout"; script = "Invoke-WholeOSN33Closeout.ps1" }
    )
}

foreach ($stage in $stages) {
    $stageRoot = Join-Path $StateRoot $stage.id
    $current = Join-Path $stageRoot "stage-current.json"
    if (Test-Path -LiteralPath $current -PathType Leaf) {
        $retained = Get-Content -LiteralPath $current -Raw | ConvertFrom-Json
        $retainedScope = if ($retained.PSObject.Properties.Name -contains "claim_scope") {
            [string]$retained.claim_scope
        } else {
            "full-autonomy-or-superiority"
        }
        if ($retainedScope -ne $ClaimScope) {
            throw "Retained $($stage.id) state belongs to claim scope $retainedScope, not $ClaimScope."
        }
        if ([string]$retained.agent_result.status -eq "complete") {
            $retainedBlockers = @($retained.agent_result.blockers)
            if ($retainedBlockers.Count -gt 0) {
                Write-Host "WHOLE-OS PIPELINE BLOCKED: $($stage.id) completed with unresolved blockers and cannot release dependent stages."
                exit 20
            }
            Write-Host "WHOLE-OS PIPELINE SKIP COMPLETE: $($stage.id)"
            continue
        }
    }

    do {
        $stageScript = Join-Path $PSScriptRoot $stage.script
        & $stageScript -Repository $repositoryRoot -StateRoot $StateRoot -Model $Model -ReasoningEffort $ReasoningEffort -ClaimScope $ClaimScope
        $stageExit = $LASTEXITCODE
        if ($stageExit -eq 0) {
            $retained = Get-Content -LiteralPath $current -Raw | ConvertFrom-Json
            $retainedBlockers = @($retained.agent_result.blockers)
            if ($retainedBlockers.Count -gt 0) {
                Write-Host "WHOLE-OS PIPELINE BLOCKED: $($stage.id) completed with unresolved blockers and cannot release dependent stages."
                exit 20
            }
            break
        }
        if ($stageExit -notin @(10, 20)) {
            throw "Whole-OS stage $($stage.id) failed with exit code $stageExit."
        }
        if ($Once) {
            Write-Host "WHOLE-OS PIPELINE PAUSED: $($stage.id) requires another pass."
            exit $stageExit
        }
        $retained = Get-Content -LiteralPath $current -Raw | ConvertFrom-Json
        $requested = [int]$retained.agent_result.retry_after_seconds
        $delay = if ($requested -ge 60 -and $requested -le 86400) { $requested } else { $DefaultRetrySeconds }
        Write-Host "WHOLE-OS PIPELINE WAIT: $($stage.id) retry in $delay seconds."
        Start-Sleep -Seconds $delay
    } while ($true)
}

Write-Host "WHOLE-OS PIPELINE COMPLETE: all $($stages.Count) claim-scoped stages reported complete."
exit 0
