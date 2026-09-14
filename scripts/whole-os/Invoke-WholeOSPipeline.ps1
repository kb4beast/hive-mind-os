[CmdletBinding()]
param(
    [string]$Repository = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "HiveMindOS\whole-os-pipeline"),
    [string]$Model = "gpt-5.6-sol",
    [ValidateSet("low", "medium", "high", "xhigh", "max", "ultra")]
    [string]$ReasoningEffort = "high",
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
        try {
            $prior = Get-Content -LiteralPath $processReceipt -Raw | ConvertFrom-Json
            if ($null -ne (Get-Process -Id ([int]$prior.process_id) -ErrorAction SilentlyContinue)) {
                Write-Host "WHOLE-OS PIPELINE ALREADY RUNNING: PID $($prior.process_id)"
                exit 0
            }
        } catch {
            Write-Verbose "Prior process receipt is stale or unreadable; starting a successor."
        }
    }
    foreach ($value in @($PSCommandPath, $repositoryRoot, $StateRoot, $Model, $ReasoningEffort)) {
        if ($value.Contains('"')) { throw "Background launcher arguments cannot contain quotes." }
    }
    $stdout = Join-Path $StateRoot "pipeline.stdout.log"
    $stderr = Join-Path $StateRoot "pipeline.stderr.log"
    $powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
    $nativeArguments = '-NoProfile -File "{0}" -Repository "{1}" -StateRoot "{2}" -Model "{3}" -ReasoningEffort "{4}" -DefaultRetrySeconds {5}' -f $PSCommandPath, $repositoryRoot, $StateRoot, $Model, $ReasoningEffort, $DefaultRetrySeconds
    if ($Once) { $nativeArguments += " -Once" }
    $process = Start-Process -FilePath $powershell -ArgumentList $nativeArguments -WorkingDirectory $repositoryRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    [ordered]@{
        schema_version = 1
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

$stages = @(
    [ordered]@{ id = "host-bootstrap"; script = "Invoke-WholeOSHostBootstrap.ps1" },
    [ordered]@{ id = "n30-tournament"; script = "Invoke-WholeOSN30Tournament.ps1" },
    [ordered]@{ id = "n31-self-pilot"; script = "Invoke-WholeOSN31SelfPilot.ps1" },
    [ordered]@{ id = "n32-external-pilot"; script = "Invoke-WholeOSN32ExternalPilot.ps1" },
    [ordered]@{ id = "n33-closeout"; script = "Invoke-WholeOSN33Closeout.ps1" }
)

foreach ($stage in $stages) {
    $stageRoot = Join-Path $StateRoot $stage.id
    $current = Join-Path $stageRoot "stage-current.json"
    if (Test-Path -LiteralPath $current -PathType Leaf) {
        $retained = Get-Content -LiteralPath $current -Raw | ConvertFrom-Json
        if ([string]$retained.agent_result.status -eq "complete") {
            Write-Host "WHOLE-OS PIPELINE SKIP COMPLETE: $($stage.id)"
            continue
        }
    }

    do {
        $stageScript = Join-Path $PSScriptRoot $stage.script
        & $stageScript -Repository $repositoryRoot -StateRoot $StateRoot -Model $Model -ReasoningEffort $ReasoningEffort
        $stageExit = $LASTEXITCODE
        if ($stageExit -eq 0) { break }
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

Write-Host "WHOLE-OS PIPELINE COMPLETE: all five stages reported complete."
exit 0
