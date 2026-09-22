[CmdletBinding()]
param(
    [string]$Repository = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "HiveMindOS\whole-os-pipeline"),
    [string]$Model = "gpt-5.6-sol",
    [string]$ReasoningEffort = "high",
    [ValidateSet("bounded-operational-production-pilot", "full-autonomy-or-superiority")]
    [string]$ClaimScope = "full-autonomy-or-superiority"
)
if ($ClaimScope -ne "full-autonomy-or-superiority") {
    throw "N30 is available only for the full-autonomy-or-superiority claim scope."
}
$runner = Join-Path $PSScriptRoot "Invoke-WholeOSAgentStage.ps1"
$prompt = Join-Path $PSScriptRoot "prompts\02-n30-tournament.md"
& $runner -Stage "n30-tournament" -PromptPath $prompt -Repository $Repository -StateRoot $StateRoot -Model $Model -ReasoningEffort $ReasoningEffort -ClaimScope $ClaimScope
exit $LASTEXITCODE
