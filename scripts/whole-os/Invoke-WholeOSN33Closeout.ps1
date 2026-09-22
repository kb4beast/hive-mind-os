[CmdletBinding()]
param(
    [string]$Repository = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "HiveMindOS\whole-os-pipeline"),
    [string]$Model = "gpt-5.6-sol",
    [string]$ReasoningEffort = "high",
    [ValidateSet("bounded-operational-production-pilot", "full-autonomy-or-superiority")]
    [string]$ClaimScope = "full-autonomy-or-superiority"
)
$runner = Join-Path $PSScriptRoot "Invoke-WholeOSAgentStage.ps1"
$prompt = Join-Path $PSScriptRoot "prompts\05-n33-closeout.md"
& $runner -Stage "n33-closeout" -PromptPath $prompt -Repository $Repository -StateRoot $StateRoot -Model $Model -ReasoningEffort $ReasoningEffort -ClaimScope $ClaimScope
exit $LASTEXITCODE
