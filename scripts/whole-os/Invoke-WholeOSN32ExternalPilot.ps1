[CmdletBinding()]
param(
    [string]$Repository = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "HiveMindOS\whole-os-pipeline"),
    [string]$Model = "gpt-5.6-sol",
    [string]$ReasoningEffort = "high"
)
$runner = Join-Path $PSScriptRoot "Invoke-WholeOSAgentStage.ps1"
$prompt = Join-Path $PSScriptRoot "prompts\04-n32-external-pilot.md"
& $runner -Stage "n32-external-pilot" -PromptPath $prompt -Repository $Repository -StateRoot $StateRoot -Model $Model -ReasoningEffort $ReasoningEffort
exit $LASTEXITCODE
