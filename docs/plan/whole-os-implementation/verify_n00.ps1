param(
    [switch]$RequireLiveCheckoutMatch
)

$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$handoff = Join-Path $repo "docs\plan\whole-os-tournament-2026-09-13"
$candidate = $PSScriptRoot

function Require([bool]$Condition, [string]$Message) {
    if (-not $Condition) {
        throw $Message
    }
}

function Read-Json([string]$Path) {
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

$manifest = Read-Json (Join-Path $handoff "MANIFEST.json")
foreach ($entry in $manifest.files) {
    $path = Join-Path $handoff $entry.path
    Require (Test-Path -LiteralPath $path) "missing handoff file: $($entry.path)"
    Require ((Get-Item -LiteralPath $path).Length -eq $entry.bytes) "wrong byte count: $($entry.path)"
    $digest = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    Require ($digest -eq $entry.sha256) "wrong handoff digest: $($entry.path)"
}

$local = Read-Json (Join-Path $handoff "local-source-manifest.json")
$pinnedTree = (git -C $repo rev-parse "$($local.commit)^{tree}").Trim()
Require ($LASTEXITCODE -eq 0) "missing pinned local-source commit: $($local.commit)"
Require ($pinnedTree -eq $local.tree) "wrong pinned local-source tree: $($local.commit)"
foreach ($entry in $local.files) {
    $blob = (git -C $repo rev-parse "$($local.commit):$($entry.path)").Trim()
    Require ($LASTEXITCODE -eq 0) "missing pinned local source: $($entry.path)"
    Require ($blob -eq $entry.git_blob) "wrong pinned local source blob: $($entry.path)"
    if ($RequireLiveCheckoutMatch) {
        $path = Join-Path $repo $entry.path
        Require (Test-Path -LiteralPath $path) "missing live local source: $($entry.path)"
        $digest = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        Require ($digest -eq $entry.checkout_sha256) "live local source drift: $($entry.path)"
        $liveBlob = (git -C $repo hash-object -- $path).Trim()
        Require ($liveBlob -eq $entry.git_blob) "live local source blob drift: $($entry.path)"
    }
}

$inventory = Read-Json (Join-Path $candidate "source-inventory.json")
$requirements = Read-Json (Join-Path $handoff "requirements.json")
$dag = Read-Json (Join-Path $handoff "dag-index.json")
$nodeMap = Read-Json (Join-Path $candidate "successor-node-map.json")
$symbols = Read-Json (Join-Path $candidate "symbol-classification.json")

$sourceIds = @($inventory.sources.id)
Require (($sourceIds | Sort-Object -Unique).Count -eq $sourceIds.Count) "duplicate successor source ID"
$requiredSources = @("OWNER-ORIGINAL-01", "OWNER-IMPLEMENTATION-01", "GOV-AGENTS-01", "GOV-VISION-01", "GOV-DOCKET-01", "GOV-DAG-01", "GOV-AUTOPILOT-01", "GOV-ADR-074", "GOV-ADR-075", "GOV-ADR-076", "GOV-ADR-077", "GOV-ADR-078", "HANDOFF-01", "LOCAL-01") + (1..18 | ForEach-Object { "EX{0:D2}" -f $_ })
Require ((Compare-Object ($sourceIds | Sort-Object) ($requiredSources | Sort-Object)).Count -eq 0) "successor source set mismatch"

foreach ($source in $inventory.sources) {
    $relative = ($source.locator -split "#")[0]
    Require (Test-Path -LiteralPath (Join-Path $repo $relative)) "unresolved source locator: $($source.locator)"
}

$requiredAdrs = 74..78 | ForEach-Object { "GOV-ADR-{0:D3}" -f $_ }
foreach ($id in $requiredAdrs) {
    $record = @($inventory.sources | Where-Object id -eq $id)
    Require ($record.Count -eq 1) "missing ADR source: $id"
    $blob = (git -C $repo rev-parse "$($inventory.repository.handoff_commit):$($record[0].locator)").Trim()
    Require ($LASTEXITCODE -eq 0) "missing pinned ADR source: $id"
    Require ($blob -eq $record[0].git_blob) "wrong ADR blob: $id"
}

foreach ($id in 9..16 | ForEach-Object { "EX{0:D2}" -f $_ }) {
    $record = @($inventory.sources | Where-Object id -eq $id)[0]
    Require (-not [string]::IsNullOrWhiteSpace($record.version)) "missing version: $id"
    Require ($record.body_sha256 -match "^[0-9a-f]{64}$") "missing body digest: $id"
    Require (-not [string]::IsNullOrWhiteSpace($record.license)) "missing license disposition: $id"
    Require ($record.ingestion -ne "complete") "external raw source falsely marked complete: $id"
}

$foundingIds = @($inventory.founding_sources.id)
$expectedFounding = 1..15 | ForEach-Object { "SRC-{0:D3}" -f $_ }
Require ($foundingIds.Count -eq 15) "wrong founding source count"
Require (($foundingIds | Sort-Object -Unique).Count -eq 15) "duplicate founding source ID"
Require ((Compare-Object ($foundingIds | Sort-Object) ($expectedFounding | Sort-Object)).Count -eq 0) "founding source set mismatch"
Require ((@($inventory.founding_sources | Where-Object id -eq "SRC-005")[0].status) -eq "pending_ingestion") "SRC-005 availability was widened"
Require ((@($inventory.founding_sources | Where-Object id -eq "SRC-006")[0].status) -eq "partial") "SRC-006 availability was widened"

$requirementIds = @($inventory.requirements.id)
$expectedRequirements = @($requirements.requirements.id)
Require ($requirementIds.Count -eq 18) "wrong requirement count"
Require (($requirementIds | Sort-Object -Unique).Count -eq 18) "duplicate requirement ID"
Require ((Compare-Object ($requirementIds | Sort-Object) ($expectedRequirements | Sort-Object)).Count -eq 0) "requirement set mismatch"
foreach ($requirement in $inventory.requirements) {
    $parts = $requirement.locator -split "#"
    Require ($parts.Count -eq 2) "requirement locator lacks anchor: $($requirement.id)"
    Require (Test-Path -LiteralPath (Join-Path $repo $parts[0])) "unresolved requirement locator: $($requirement.id)"
    Require ($parts[1] -eq $requirement.id) "wrong requirement anchor: $($requirement.id)"
}

$dagIds = @($dag.nodes.id)
$mapIds = @($nodeMap.nodes.id)
$symbolIds = @($symbols.nodes.node)
Require ($dagIds.Count -eq 34) "wrong DAG node count"
Require (($dagIds | Sort-Object -Unique).Count -eq 34) "duplicate DAG node ID"
Require ((Compare-Object ($dagIds | Sort-Object) ($mapIds | Sort-Object)).Count -eq 0) "successor node map mismatch"
Require ((Compare-Object ($dagIds | Sort-Object) ($symbolIds | Sort-Object)).Count -eq 0) "symbol classification node mismatch"
foreach ($entry in $symbols.nodes) {
    Require (-not [string]::IsNullOrWhiteSpace($entry.locator_or_symbol)) "missing symbol locator: $($entry.node)"
    Require (-not [string]::IsNullOrWhiteSpace($entry.classification)) "missing classification: $($entry.node)"
    Require (-not [string]::IsNullOrWhiteSpace($entry.evidence_path)) "missing evidence path: $($entry.node)"
    Require (-not [string]::IsNullOrWhiteSpace($entry.caller_or_test)) "missing test/caller disposition: $($entry.node)"
}

[ordered]@{
    schema = "whole-os-n00-check/v1"
    result = "PASS"
    handoff_manifest_files = $manifest.files.Count
    local_source_paths = $local.files.Count
    local_source_mode = $(if ($RequireLiveCheckoutMatch) { "pinned_and_live" } else { "pinned_snapshot" })
    successor_sources = $sourceIds.Count
    founding_sources = $foundingIds.Count
    requirements = $requirementIds.Count
    nodes = $dagIds.Count
    symbol_classifications = $symbolIds.Count
} | ConvertTo-Json
