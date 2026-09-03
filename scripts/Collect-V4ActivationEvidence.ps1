[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [switch]$AllowDirty,
    [ValidateRange(1, 900)][int]$FocusedTestTimeoutSeconds = 180,
    [ValidateRange(1, 60000)][int]$MaximumFocusedModuleTimeoutMilliseconds = 60000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Utf8File {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Content
    )

    $encoding = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][object]$Value
    )

    Write-Utf8File -Path $Path -Content ($Value | ConvertTo-Json -Depth 16)
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $stream = [System.IO.File]::OpenRead($Path)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $hasher.ComputeHash($stream)
    }
    finally {
        $hasher.Dispose()
        $stream.Dispose()
    }
    return 'sha256:' + ([System.BitConverter]::ToString($hash).Replace('-', '').ToLowerInvariant())
}

function Get-TextSha256 {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)

    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Text)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $hasher.ComputeHash($bytes)
    }
    finally {
        $hasher.Dispose()
    }
    return 'sha256:' + ([System.BitConverter]::ToString($hash).Replace('-', '').ToLowerInvariant())
}

function Resolve-Application {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Get-Command -Name $Name -CommandType Application -ErrorAction Stop |
        Select-Object -First 1
    $resolved = [System.IO.Path]::GetFullPath($command.Source)
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        throw "Resolved application is not a file: $resolved"
    }
    return $resolved
}

$processRunnerPath = Join-Path $PSScriptRoot 'V4EvidenceProcess.ps1'
if (-not (Test-Path -LiteralPath $processRunnerPath -PathType Leaf)) {
    throw "Required focused-test process runner is missing: $processRunnerPath"
}
. $processRunnerPath

function Test-IsInside {
    param(
        [Parameter(Mandatory = $true)][string]$Candidate,
        [Parameter(Mandatory = $true)][string]$Parent
    )

    $candidatePath = [System.IO.Path]::GetFullPath($Candidate).TrimEnd('\', '/')
    $parentPath = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\', '/')
    if ($candidatePath.Equals($parentPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    return $candidatePath.StartsWith(
        $parentPath + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Test-IsFullyQualifiedFileSystemPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not [System.IO.Path]::IsPathRooted($Path)) {
        return $false
    }
    $root = [System.IO.Path]::GetPathRoot($Path)
    return (
        $root -match '^[A-Za-z]:[\\/]$' -or
        $root -match '^\\\\[^\\/]+[\\/][^\\/]+[\\/]?$'
    )
}

function Assert-NoReparsePointAncestor {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $current = [System.IO.Path]::GetFullPath($Path)
    while (-not [string]::IsNullOrEmpty($current)) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (
                ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq
                [System.IO.FileAttributes]::ReparsePoint
            ) {
                throw "$Label traverses a reparse point and cannot be physically contained: $current"
            }
        }
        $parent = [System.IO.Directory]::GetParent($current)
        if ($null -eq $parent) {
            break
        }
        $current = $parent.FullName
    }
}

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$manifestPath = Join-Path $repositoryRoot 'docs\execution\dags\generic-hive-mind-product-v4\manifest.json'
$planPath = Join-Path $repositoryRoot 'docs\execution\dags\generic-hive-mind-product-v4\plan.json'
$sourceIntakePath = Join-Path $repositoryRoot 'evidence\audits\v4-successor-recovery\SOURCE-INTAKE.json'
$sourceArchivePath = Join-Path $repositoryRoot 'evidence\sources\v4-successor-recovery\SOURCE-ARCHIVE.json'
$standardPath = Join-Path $repositoryRoot 'docs\execution\DAG_AUTHORING_STANDARD_V2.md'
$gitExecutable = Resolve-Application -Name 'git'
$pythonExecutable = Resolve-Application -Name 'python'
$pythonSha256Before = Get-Sha256 -Path $pythonExecutable
$taskkillExecutable = [System.IO.Path]::GetFullPath(
    (Join-Path ([Environment]::SystemDirectory) 'taskkill.exe')
)
if (-not (Test-Path -LiteralPath $taskkillExecutable -PathType Leaf)) {
    throw "Required process-tree terminator is missing: $taskkillExecutable"
}

function Invoke-PinnedGit {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = & $gitExecutable --no-pager -C $repositoryRoot `
        -c 'core.fsmonitor=false' `
        -c 'core.hooksPath=NUL' `
        -c 'core.untrackedCache=false' `
        -c 'diff.external=' `
        @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Pinned Git failed for arguments [$($Arguments -join ', ')]: $($output -join [Environment]::NewLine)"
    }
    return @($output | ForEach-Object { $_.ToString() })
}

foreach ($requiredPath in @($manifestPath, $planPath, $sourceIntakePath, $sourceArchivePath, $standardPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required V4 input is missing: $requiredPath"
    }
}

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $OutputDirectory = Join-Path ([System.IO.Path]::GetTempPath()) "hive-mind-v4-evidence-$stamp"
}
elseif (-not (Test-IsFullyQualifiedFileSystemPath -Path $OutputDirectory)) {
    throw 'An explicit OutputDirectory must be a fully qualified absolute filesystem path.'
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
Assert-NoReparsePointAncestor -Path $repositoryRoot -Label 'Repository root'
Assert-NoReparsePointAncestor -Path $OutputDirectory -Label 'OutputDirectory'
foreach ($requiredPath in @($manifestPath, $planPath, $sourceIntakePath, $sourceArchivePath, $standardPath)) {
    Assert-NoReparsePointAncestor -Path $requiredPath -Label 'Required V4 input'
}
if (Test-IsInside -Candidate $OutputDirectory -Parent $repositoryRoot) {
    throw 'OutputDirectory must be outside the repository.'
}
if (Test-Path -LiteralPath $OutputDirectory) {
    throw "OutputDirectory already exists: $OutputDirectory"
}

$inheritedGitEnvironment = @{}
foreach ($entry in @(Get-ChildItem Env:)) {
    if ($entry.Name.StartsWith('GIT_', [System.StringComparison]::OrdinalIgnoreCase)) {
        $inheritedGitEnvironment[$entry.Name] = $entry.Value
        Remove-Item -LiteralPath "Env:$($entry.Name)"
    }
}
$previousPythonPath = $env:PYTHONPATH
$previousNoBytecode = $env:PYTHONDONTWRITEBYTECODE

try {
    $statusBefore = @(Invoke-PinnedGit -Arguments @('status', '--porcelain=v1', '--untracked-files=all'))
    $worktreeCleanBefore = $statusBefore.Count -eq 0
    if (-not $worktreeCleanBefore -and -not $AllowDirty) {
        throw 'Working tree is not clean. Use a frozen commit or -AllowDirty for a non-qualifying package.'
    }

    [void][System.IO.Directory]::CreateDirectory($OutputDirectory)
    Assert-NoReparsePointAncestor -Path $OutputDirectory -Label 'OutputDirectory'
    $manifestText = [System.IO.File]::ReadAllText(
        $manifestPath,
        [System.Text.UTF8Encoding]::new($false)
    )
    $manifest = $manifestText | ConvertFrom-Json
    $plan = [System.IO.File]::ReadAllText(
        $planPath,
        [System.Text.UTF8Encoding]::new($false)
    ) | ConvertFrom-Json
    $sourceIntake = [System.IO.File]::ReadAllText(
        $sourceIntakePath,
        [System.Text.UTF8Encoding]::new($false)
    ) | ConvertFrom-Json
    $sourceArchive = [System.IO.File]::ReadAllText(
        $sourceArchivePath,
        [System.Text.UTF8Encoding]::new($false)
    ) | ConvertFrom-Json
    $predecessorReceiptRelative = [string]$manifest.predecessor.qualification_receipt_path
    if ($predecessorReceiptRelative -cne 'evidence/audits/generic-v3-baseline-recovery/V3-R4-QUALIFICATION.json') {
        throw 'V3 predecessor qualification receipt path is not canonical.'
    }
    $predecessorReceiptPath = [System.IO.Path]::GetFullPath(
        (Join-Path $repositoryRoot $predecessorReceiptRelative)
    )
    Assert-NoReparsePointAncestor -Path $predecessorReceiptPath -Label 'V3 predecessor qualification receipt'
    if (
        -not (Test-IsInside -Candidate $predecessorReceiptPath -Parent $repositoryRoot) -or
        -not (Test-Path -LiteralPath $predecessorReceiptPath -PathType Leaf)
    ) {
        throw "V3 predecessor qualification receipt is missing or escapes the repository: $predecessorReceiptPath"
    }
    $predecessorReceiptSha256 = Get-Sha256 -Path $predecessorReceiptPath
    $predecessorReceiptMatches = (
        [string]$manifest.predecessor.qualification_receipt_sha256 -ceq $predecessorReceiptSha256
    )

    $head = (Invoke-PinnedGit -Arguments @('rev-parse', 'HEAD') | Select-Object -First 1)
    $tree = (Invoke-PinnedGit -Arguments @('rev-parse', 'HEAD^{tree}') | Select-Object -First 1)
    $parentLine = (Invoke-PinnedGit -Arguments @('rev-list', '--parents', '-n', '1', 'HEAD') | Select-Object -First 1)
    $parentTokens = @($parentLine -split '\s+' | Where-Object { $_ })
    if ($parentTokens.Count -ne 2 -or $parentTokens[0] -cne $head) {
        throw 'The V4 candidate must be exactly one direct-child commit with one sole parent.'
    }
    $parent = $parentTokens[1]
    $parentTree = (Invoke-PinnedGit -Arguments @('rev-parse', "$parent^{tree}") | Select-Object -First 1)
    $soleParentVerified = $true
    $branch = (Invoke-PinnedGit -Arguments @('branch', '--show-current') | Select-Object -First 1)
    $changedPaths = @(Invoke-PinnedGit -Arguments @(
        'diff-tree', '--no-commit-id', '--name-only', '-r', '--no-renames', 'HEAD'
    ))
    $trackedInventory = @(Invoke-PinnedGit -Arguments @('ls-tree', '-r', '--full-tree', 'HEAD'))

    $bytecodeBefore = @(
        Get-ChildItem -LiteralPath $repositoryRoot -Recurse -Force -ErrorAction Stop |
            Where-Object {
                ($_.PSIsContainer -and $_.Name -ceq '__pycache__') -or
                (-not $_.PSIsContainer -and $_.Extension -ieq '.pyc')
            } |
            ForEach-Object { $_.FullName }
    )

    $focusedTestExpectations = [ordered]@{
        'tests.test_adapter_registry' = 7
        'tests.test_ci_contract' = 11
        'tests.test_control_token_economy' = 14
        'tests.test_dag_executor' = 23
        'tests.test_dag_standard_product' = 5
        'tests.test_generic_dag_failure_matrix' = 5
        'tests.test_generic_dag_fixtures' = 3
        'tests.test_generic_dag_token_benchmark' = 3
        'tests.test_generic_dag_v4_activation' = 14
        'tests.test_generic_dag_v4_plan' = 4
        'tests.test_hive_cortex_role_applicability' = 11
        'tests.test_hive_cortex_token_economy' = 11
        'tests.test_host_runtime' = 57
        'tests.test_integration_transaction' = 34
        'tests.test_plan_generation' = 5
        'tests.test_plan_lineage' = 7
        'tests.test_planner_prompt' = 2
        'tests.test_portable_plan' = 7
        'tests.test_powershell_preparation' = 4
        'tests.test_public_dag_cli' = 4
        'tests.test_repository_index' = 5
        'tests.test_resource_adapter' = 6
        'tests.test_runtime_contracts' = 8
        'tests.test_sidecar_calibration' = 5
        'tests.test_subject_adapter' = 6
        'tests.test_subject_execution' = 7
        'tests.test_task_reuse' = 7
        'tests.test_v4_source_provenance' = 7
        'tests.test_wave_runtime' = 11
    }
    $focusedTestModules = @($focusedTestExpectations.Keys)
    $expectedFocusedTestCount = [int](
        ($focusedTestExpectations.Values | Measure-Object -Sum).Sum
    )
    $testOutputPath = Join-Path $OutputDirectory 'focused-test-output.txt'
    $testStdoutPath = Join-Path $OutputDirectory 'focused-test-stdout.txt'
    $testStderrPath = Join-Path $OutputDirectory 'focused-test-stderr.txt'
    $testBootstrapPath = Join-Path $OutputDirectory 'focused-test-bootstrap.py'
    $testResultMarker = 'HIVE_V4_UNITTEST_RESULT_' + [Guid]::NewGuid().ToString('N')
    $pythonExecutableLiteral = ConvertTo-Json -Compress -InputObject $pythonExecutable
    $repositoryRootLiteral = ConvertTo-Json -Compress -InputObject $repositoryRoot
    $testResultMarkerLiteral = ConvertTo-Json -Compress -InputObject $testResultMarker
    $testBootstrap = @"
from __future__ import annotations

import importlib
import faulthandler
import gc
import os
import pathlib
import sys
import unittest

EXPECTED_EXECUTABLE = pathlib.Path($pythonExecutableLiteral).resolve()
REPOSITORY_ROOT = pathlib.Path($repositoryRootLiteral).resolve()
SOURCE_ROOT = (REPOSITORY_ROOT / "src").resolve()
RESULT_MARKER = $testResultMarkerLiteral
EXPECTED_CHILD_PYTHONPATH = str(SOURCE_ROOT) + os.pathsep + str(REPOSITORY_ROOT)
if pathlib.Path(sys.executable).resolve() != EXPECTED_EXECUTABLE:
    raise SystemExit("focused validation used an unexpected Python executable")
if os.environ.get("PYTHONPATH") != EXPECTED_CHILD_PYTHONPATH:
    raise SystemExit("focused validation did not bind the child Python source path")
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(SOURCE_ROOT))
package = importlib.import_module("hive_mind_os")
expected_package = (SOURCE_ROOT / "hive_mind_os" / "__init__.py").resolve()
if pathlib.Path(package.__file__).resolve() != expected_package:
    raise SystemExit("focused validation imported hive_mind_os from another checkout")
print(f"BOUND_PYTHON={pathlib.Path(sys.executable).resolve()}", flush=True)
print(f"BOUND_PACKAGE={pathlib.Path(package.__file__).resolve()}", flush=True)
faulthandler.dump_traceback_later(15, repeat=True)
try:
    program = unittest.main(module=None, exit=False)
finally:
    faulthandler.cancel_dump_traceback_later()
gc.collect()
successful = program.result.wasSuccessful()
print(
    f"{RESULT_MARKER} tests_run={program.result.testsRun} "
    f"failures={len(program.result.failures)} "
    f"errors={len(program.result.errors)} "
    f"skipped={len(program.result.skipped)} "
    f"expected_failures={len(program.result.expectedFailures)} "
    f"unexpected_successes={len(program.result.unexpectedSuccesses)} "
    f"successful={str(successful).lower()}",
    flush=True,
)
if not successful:
    raise SystemExit(1)
"@
    Write-Utf8File -Path $testBootstrapPath -Content $testBootstrap
    Write-Utf8File -Path $testStdoutPath -Content ''
    Write-Utf8File -Path $testStderrPath -Content ''
    Write-Utf8File -Path $testOutputPath -Content ''
    $testModuleResults = @()
    $testStdoutFrames = @()
    $testStderrFrames = @()
    $testOutputFrames = @()
    $testTotalCount = 0
    $testFailureCount = 0
    $testErrorCount = 0
    $testSkippedCount = 0
    $testExpectedFailureCount = 0
    $testUnexpectedSuccessCount = 0
    $testResourceWarningStderrOccurrenceCount = 0
    $testUnraisableExceptionStderrOccurrenceCount = 0
    $testExitCode = 0
    $testActualExitCode = $null
    $testTimedOut = $false
    $testTimeoutScope = $null
    $timedOutModule = $null
    $deadlineExhaustedBeforeModule = $null
    $testTerminationExitCode = $null
    $testTerminationOutput = @()
    $validationStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    foreach ($module in $focusedTestModules) {
        $remainingMilliseconds = [int][Math]::Floor(
            ($FocusedTestTimeoutSeconds * 1000) -
            $validationStopwatch.Elapsed.TotalMilliseconds
        )
        if ($remainingMilliseconds -lt 1) {
            $testTimedOut = $true
            $testTimeoutScope = 'overall_deadline_before_module'
            $deadlineExhaustedBeforeModule = $module
            $testActualExitCode = $null
            $testExitCode = 124
            $testStdoutFrames += "=== MODULE $module ===`nMODULE_NOT_STARTED_OVERALL_DEADLINE_EXHAUSTED"
            $testStderrFrames += "=== MODULE $module ===`nMODULE_NOT_STARTED_OVERALL_DEADLINE_EXHAUSTED"
            $testOutputFrames += "=== MODULE $module ===`nOVERALL_VALIDATION_DEADLINE_EXHAUSTED"
            Write-Utf8File -Path $testStdoutPath -Content ($testStdoutFrames -join "`n")
            Write-Utf8File -Path $testStderrPath -Content ($testStderrFrames -join "`n")
            Write-Utf8File -Path $testOutputPath -Content ($testOutputFrames -join "`n")
            break
        }
        $moduleTimeoutMilliseconds = [int][Math]::Min(
            $MaximumFocusedModuleTimeoutMilliseconds,
            $remainingMilliseconds
        )
        $frameIndex = $testOutputFrames.Count
        $testStdoutFrames += "=== MODULE $module ===`nMODULE_VALIDATION_STARTED_CHILD_OUTPUT_PENDING"
        $testStderrFrames += "=== MODULE $module ===`nMODULE_VALIDATION_STARTED_CHILD_OUTPUT_PENDING"
        $testOutputFrames += "=== MODULE $module ===`nMODULE_VALIDATION_STARTED_CHILD_OUTPUT_PENDING"
        Write-Utf8File -Path $testStdoutPath -Content ($testStdoutFrames -join "`n")
        Write-Utf8File -Path $testStderrPath -Content ($testStderrFrames -join "`n")
        Write-Utf8File -Path $testOutputPath -Content ($testOutputFrames -join "`n")
        $moduleResult = Invoke-BoundedPythonValidation `
            -PythonExecutable $pythonExecutable `
            -BootstrapPath $testBootstrapPath `
            -Modules @($module) `
            -WorkingDirectory $repositoryRoot `
            -TaskkillExecutable $taskkillExecutable `
            -TimeoutMilliseconds $moduleTimeoutMilliseconds
        $testActualExitCode = $moduleResult.actual_exit_code
        $testStdoutFrames[$frameIndex] = "=== MODULE $module ===`n$($moduleResult.stdout)"
        $testStderrFrames[$frameIndex] = "=== MODULE $module ===`n$($moduleResult.stderr)"
        $testOutputFrames[$frameIndex] = (
            "=== MODULE $module ===`n=== STDOUT ===`n$($moduleResult.stdout)" +
            "`n=== STDERR ===`n$($moduleResult.stderr)"
        )
        Write-Utf8File -Path $testStdoutPath -Content ($testStdoutFrames -join "`n")
        Write-Utf8File -Path $testStderrPath -Content ($testStderrFrames -join "`n")
        Write-Utf8File -Path $testOutputPath -Content ($testOutputFrames -join "`n")
        $expectedModuleTestCount = [int]$focusedTestExpectations[$module]
        $terminalResult = Get-V4UnittestTerminalResult `
            -Stdout ([string]$moduleResult.stdout) `
            -Stderr ([string]$moduleResult.stderr) `
            -Marker $testResultMarker `
            -ExpectedTestsRun $expectedModuleTestCount
        $testTotalCount += $terminalResult.tests_run
        $testFailureCount += $terminalResult.failures
        $testErrorCount += $terminalResult.errors
        $testSkippedCount += $terminalResult.skipped
        $testExpectedFailureCount += $terminalResult.expected_failures
        $testUnexpectedSuccessCount += $terminalResult.unexpected_successes
        $testResourceWarningStderrOccurrenceCount += (
            $terminalResult.resource_warning_stderr_occurrence_count
        )
        $testUnraisableExceptionStderrOccurrenceCount += (
            $terminalResult.unraisable_exception_stderr_occurrence_count
        )
        $testModuleResults += [pscustomobject][ordered]@{
            module = $module
            tests_run = $terminalResult.tests_run
            expected_tests_run = $terminalResult.expected_tests_run
            test_count_matches_expected = $terminalResult.test_count_matches_expected
            failures = $terminalResult.failures
            errors = $terminalResult.errors
            skipped = $terminalResult.skipped
            expected_failures = $terminalResult.expected_failures
            unexpected_successes = $terminalResult.unexpected_successes
            resource_warning_stderr_occurrence_count = (
                $terminalResult.resource_warning_stderr_occurrence_count
            )
            unraisable_exception_stderr_occurrence_count = (
                $terminalResult.unraisable_exception_stderr_occurrence_count
            )
            terminal_result_marker_count = $terminalResult.marker_count
            terminal_result_success = $terminalResult.successful
            terminal_result_outcomes_clean = $terminalResult.outcomes_clean
            terminal_result_valid = $terminalResult.valid
            child_pid = $moduleResult.child_pid
            timeout_seconds = $moduleResult.timeout_seconds
            timeout_milliseconds = $moduleResult.timeout_milliseconds
            duration_milliseconds = $moduleResult.duration_milliseconds
            actual_exit_code = $moduleResult.actual_exit_code
            effective_exit_code = $moduleResult.effective_exit_code
            timed_out = $moduleResult.timed_out
            termination_exit_code = $moduleResult.termination_exit_code
            termination_output = @($moduleResult.termination_output)
            stdout_sha256 = Get-TextSha256 -Text ([string]$moduleResult.stdout)
            stderr_sha256 = Get-TextSha256 -Text ([string]$moduleResult.stderr)
            child_pythonpath = $moduleResult.child_pythonpath
            removed_python_environment_names = @(
                $moduleResult.removed_python_environment_names
            )
        }
        if ($moduleResult.timed_out) {
            $testTimedOut = $true
            $testTimeoutScope = 'module_process'
            $timedOutModule = $module
            $testExitCode = 124
            $testTerminationExitCode = $moduleResult.termination_exit_code
            $testTerminationOutput = @($moduleResult.termination_output)
            break
        }
        if ($moduleResult.effective_exit_code -ne 0) {
            $testExitCode = $moduleResult.effective_exit_code
            break
        }
    }
    $validationStopwatch.Stop()
    $completedModuleCount = @(
        $testModuleResults |
            Where-Object {
                -not $_.timed_out -and
                $_.effective_exit_code -eq 0 -and
                $_.terminal_result_valid
            }
    ).Count
    $allFocusedModulesCompleted = (
        $testModuleResults.Count -eq $focusedTestModules.Count -and
        $completedModuleCount -eq $focusedTestModules.Count
    )
    if (-not $allFocusedModulesCompleted -and $testExitCode -eq 0) {
        $testExitCode = 125
    }
    $testCountMatchesExpected = $testTotalCount -eq $expectedFocusedTestCount
    $terminalOutcomesClean = (
        $testFailureCount -eq 0 -and
        $testErrorCount -eq 0 -and
        $testSkippedCount -eq 0 -and
        $testExpectedFailureCount -eq 0 -and
        $testUnexpectedSuccessCount -eq 0 -and
        $testResourceWarningStderrOccurrenceCount -eq 0 -and
        $testUnraisableExceptionStderrOccurrenceCount -eq 0
    )
    $removedPythonEnvironmentNames = @(
        $testModuleResults |
            ForEach-Object { $_.removed_python_environment_names } |
            Sort-Object -Unique
    )
    $expectedChildPythonPath = (
        (Join-Path $repositoryRoot 'src') +
        [System.IO.Path]::PathSeparator +
        $repositoryRoot
    )
    $childPythonPathConsistent = (
        $testModuleResults.Count -gt 0 -and
        @(
            $testModuleResults |
                Where-Object { $_.child_pythonpath -cne $expectedChildPythonPath }
        ).Count -eq 0
    )
    Write-Utf8File -Path $testStdoutPath -Content ($testStdoutFrames -join "`n")
    Write-Utf8File -Path $testStderrPath -Content ($testStderrFrames -join "`n")
    Write-Utf8File -Path $testOutputPath -Content ($testOutputFrames -join "`n")
    $pythonSha256After = Get-Sha256 -Path $pythonExecutable
    $pythonExecutableStable = $pythonSha256Before -ceq $pythonSha256After

    $statusAfter = @(Invoke-PinnedGit -Arguments @('status', '--porcelain=v1', '--untracked-files=all'))
    $worktreeCleanAfter = $statusAfter.Count -eq 0
    $bytecodeAfter = @(
        Get-ChildItem -LiteralPath $repositoryRoot -Recurse -Force -ErrorAction Stop |
            Where-Object {
                ($_.PSIsContainer -and $_.Name -ceq '__pycache__') -or
                (-not $_.PSIsContainer -and $_.Extension -ieq '.pyc')
            } |
            ForEach-Object { $_.FullName }
    )

    $manifestSha256 = Get-Sha256 -Path $manifestPath
    $planSha256 = Get-Sha256 -Path $planPath
    $sourceIntakeSha256 = Get-Sha256 -Path $sourceIntakePath
    $sourceArchiveSha256 = Get-Sha256 -Path $sourceArchivePath
    $requestSha256 = Get-TextSha256 -Text ([string]$manifest.request_text
    )
    # The manifest's candidate_base is always the sole parent of the candidate
    # commit.  Dirty diagnostic collection may make the checked-out tree differ
    # from HEAD, but it must not redefine the candidate's immutable base.
    $candidateBaseObservedCommit = $parent
    $candidateBaseObservedTree = $parentTree
    $candidateBaseReferenceMode = 'candidate-sole-parent'
    $candidateBaseMatches = (
        [string]$manifest.candidate_base.commit -ceq $candidateBaseObservedCommit -and
        [string]$manifest.candidate_base.tree -ceq $candidateBaseObservedTree
    )
    $planMatches = (
        [string]$manifest.plan.sha256 -ceq $planSha256 -and
        [int]$manifest.plan.node_count -eq @($plan.nodes).Count -and
        [string]$manifest.request_sha256 -ceq $requestSha256 -and
        [string]$plan.request_id -ceq $requestSha256 -and
        [string]$manifest.repository_id -ceq [string]$plan.subject.repository.repository_id -and
        [string]$manifest.source_intake.path -ceq 'evidence/audits/v4-successor-recovery/SOURCE-INTAKE.json' -and
        [string]$manifest.source_intake.sha256 -ceq $sourceIntakeSha256 -and
        [string]$manifest.source_intake.archive_path -ceq 'evidence/sources/v4-successor-recovery/SOURCE-ARCHIVE.json' -and
        [string]$manifest.source_intake.archive_sha256 -ceq $sourceArchiveSha256 -and
        [int]$manifest.source_intake.source_count -eq @($sourceIntake.sources).Count -and
        [int]$manifest.source_intake.unavailable_source_count -eq @($sourceIntake.unavailable_sources).Count -and
        [string]$sourceIntake.source_archive.sha256 -ceq $sourceArchiveSha256 -and
        (@($sourceArchive.sources | ForEach-Object { [string]$_.source_id }) -join "`n") -ceq (@($sourceIntake.source_archive.source_ids) -join "`n") -and
        $predecessorReceiptMatches
    )
    $inertManifest = (
        [int]$manifest.schema_version -eq 2 -and
        [string]$manifest.status -ceq 'CANDIDATE_NOT_AUTHORIZED' -and
        [bool]$manifest.execution_authorized -eq $false -and
        [bool]$manifest.activation_policy.protected_merge_authorized -eq $false
    )
    $qualificationEligible = (
        -not $testTimedOut -and
        $testExitCode -eq 0 -and
        $allFocusedModulesCompleted -and
        $testCountMatchesExpected -and
        $terminalOutcomesClean -and
        $childPythonPathConsistent -and
        $pythonExecutableStable -and
        $worktreeCleanBefore -and
        $worktreeCleanAfter -and
        $bytecodeBefore.Count -eq 0 -and
        $bytecodeAfter.Count -eq 0 -and
        $candidateBaseMatches -and
        $planMatches -and
        $inertManifest -and
        $branch.StartsWith('codex/', [System.StringComparison]::Ordinal)
    )
    $capturedAt = [DateTime]::UtcNow.ToString('o')

    $hostObservationPath = Join-Path $OutputDirectory 'host-observation.json'
    $hostObservation = [ordered]@{
        schema_version = 2
        kind = 'hive-mind-local-host-observation-v2'
        captured_at_utc = $capturedAt
        machine_name = [Environment]::MachineName
        os_version = [Environment]::OSVersion.VersionString
        powershell_version = $PSVersionTable.PSVersion.ToString()
        processor_count = [Environment]::ProcessorCount
        git = [ordered]@{
            path = $gitExecutable
            sha256 = Get-Sha256 -Path $gitExecutable
            version = (Invoke-PinnedGit -Arguments @('--version') | Select-Object -First 1)
        }
        python = [ordered]@{
            path = $pythonExecutable
            sha256 = Get-Sha256 -Path $pythonExecutable
            version = (& $pythonExecutable '--version' 2>&1 | Select-Object -First 1).ToString()
        }
        worktree_clean = $worktreeCleanAfter
        bytecode_free = $bytecodeAfter.Count -eq 0
        read_only_custody = $false
        attestation = 'LOCAL_OBSERVATION_ONLY_NOT_FROZEN_HOST_EVIDENCE'
    }
    Write-JsonFile -Path $hostObservationPath -Value $hostObservation

    $templatePath = Join-Path $OutputDirectory 'unsigned-activation-template.json'
    $template = [ordered]@{
        schema_version = 1
        kind = 'hive-mind-v4-unsigned-activation-template-v1'
        executable = $false
        candidate = [ordered]@{
            branch = $branch
            commit = $head
            tree = $tree
            parent_commit = $parent
            parent_tree = $parentTree
            sole_parent_verified = $soleParentVerified
            manifest_sha256 = $manifestSha256
            plan_sha256 = $planSha256
            source_intake_sha256 = $sourceIntakeSha256
            source_archive_sha256 = $sourceArchiveSha256
            source_count = @($sourceIntake.sources).Count
            unavailable_source_count = @($sourceIntake.unavailable_sources).Count
        }
        predecessor = $manifest.predecessor
        required_external_values = [ordered]@{
            independent_review_record = $null
            frozen_host_attestation = $null
            issuer_signature = $null
            globally_unique_nonce = $null
            lease_not_more_than_seconds = 900
        }
        prohibited = @(
            'repository-generated signatures',
            'repository-owned nonce reservation',
            'protected merge',
            'production mutation'
        )
    }
    Write-JsonFile -Path $templatePath -Value $template

    $reviewRequestPath = Join-Path $OutputDirectory 'independent-review-request.md'
    $reviewRequest = @"
# Independent review request: Generic Hive Mind Product V4

This is a local evidence package, not an approval, attestation, activation bundle,
signature, nonce reservation, or authority grant.

- Candidate commit: $head
- Candidate tree: $tree
- Candidate parent: $parent
- Candidate parent tree: $parentTree
- Manifest SHA-256: $manifestSha256
- Plan SHA-256: $planSha256
- V3 qualification receipt SHA-256: $predecessorReceiptSha256
- Focused-test transcript SHA-256: $(Get-Sha256 -Path $testOutputPath)
- Locally qualification-eligible: $qualificationEligible

The independent reviewer must obtain the exact commit separately, reproduce the
tests, inspect the complete diff and threat model, and issue a separately signed
record. A different trusted host must attest immutable read-only custody. A third
external issuer must then sign the complete maximum-15-minute one-run bundle, after
which host-owned storage must atomically consume its globally unique nonce. None of
those external facts can be supplied by this repository.
"@
    Write-Utf8File -Path $reviewRequestPath -Content $reviewRequest

    $evidencePath = Join-Path $OutputDirectory 'evidence.json'
    $evidence = [ordered]@{
        schema_version = 2
        kind = 'hive-mind-v4-qualification-preparation-v2'
        captured_at_utc = $capturedAt
        qualification_eligible = $qualificationEligible
        activation_authorized = $false
        activation_status = 'CANDIDATE_NOT_AUTHORIZED'
        repository = [ordered]@{
            branch = $branch
            head_commit = $head
            head_tree = $tree
            parent_commit = $parent
            parent_tree = $parentTree
            sole_parent_verified = $soleParentVerified
            candidate_base_matches_manifest = $candidateBaseMatches
            candidate_base_reference_mode = $candidateBaseReferenceMode
            worktree_clean_before = $worktreeCleanBefore
            worktree_clean_after = $worktreeCleanAfter
            dirty_collection_requested = [bool]$AllowDirty
            status_before = $statusBefore
            status_after = $statusAfter
            changed_paths = $changedPaths
            tracked_inventory_sha256 = Get-TextSha256 -Text ($trackedInventory -join "`n")
        }
        artifacts = [ordered]@{
            manifest_sha256 = $manifestSha256
            plan_sha256 = $planSha256
            request_sha256 = $requestSha256
            source_intake_path = 'evidence/audits/v4-successor-recovery/SOURCE-INTAKE.json'
            source_intake_sha256 = $sourceIntakeSha256
            source_archive_path = 'evidence/sources/v4-successor-recovery/SOURCE-ARCHIVE.json'
            source_archive_sha256 = $sourceArchiveSha256
            source_count = @($sourceIntake.sources).Count
            unavailable_source_count = @($sourceIntake.unavailable_sources).Count
            manifest_plan_matches = $planMatches
            manifest_inert = $inertManifest
            predecessor = $manifest.predecessor
            predecessor_receipt_path = $predecessorReceiptRelative
            predecessor_receipt_sha256 = $predecessorReceiptSha256
            predecessor_receipt_matches_manifest = $predecessorReceiptMatches
        }
        toolchain = [ordered]@{
            git_path = $gitExecutable
            git_sha256 = Get-Sha256 -Path $gitExecutable
            python_path = $pythonExecutable
            python_sha256_before = $pythonSha256Before
            python_sha256_after = $pythonSha256After
            python_executable_stable = $pythonExecutableStable
            taskkill_path = $taskkillExecutable
            taskkill_sha256 = Get-Sha256 -Path $taskkillExecutable
            inherited_git_environment_names_removed = @($inheritedGitEnvironment.Keys | Sort-Object)
            inherited_python_environment_names_removed_from_child = $removedPythonEnvironmentNames
            child_pythonpath = $expectedChildPythonPath
            child_pythonpath_consistent = $childPythonPathConsistent
        }
        validation = [ordered]@{
            command = "$pythonExecutable -I -B -X utf8 -W error::ResourceWarning $testBootstrapPath -v <one fresh child per focused module; forced finalizer collection and captured-stderr zero ResourceWarning:/Exception ignored occurrence enforcement>"
            module_count = $focusedTestModules.Count
            modules = $focusedTestModules
            module_process_isolation = $true
            terminal_result_marker = $testResultMarker
            attempted_module_count = $testModuleResults.Count
            completed_module_count = $completedModuleCount
            all_modules_completed = $allFocusedModulesCompleted
            tests_run = $testTotalCount
            expected_tests_run = $expectedFocusedTestCount
            test_count_matches_expected = $testCountMatchesExpected
            failures = $testFailureCount
            errors = $testErrorCount
            skipped = $testSkippedCount
            expected_failures = $testExpectedFailureCount
            unexpected_successes = $testUnexpectedSuccessCount
            resource_warning_stderr_occurrence_count = (
                $testResourceWarningStderrOccurrenceCount
            )
            unraisable_exception_stderr_occurrence_count = (
                $testUnraisableExceptionStderrOccurrenceCount
            )
            terminal_outcomes_clean = $terminalOutcomesClean
            exit_code = $testExitCode
            actual_exit_code = $testActualExitCode
            timed_out = $testTimedOut
            timeout_scope = $testTimeoutScope
            timed_out_module = $timedOutModule
            deadline_exhausted_before_module = $deadlineExhaustedBeforeModule
            timeout_seconds = $FocusedTestTimeoutSeconds
            timeout_milliseconds = $FocusedTestTimeoutSeconds * 1000
            maximum_module_timeout_seconds = (
                $MaximumFocusedModuleTimeoutMilliseconds / 1000.0
            )
            maximum_module_timeout_milliseconds = $MaximumFocusedModuleTimeoutMilliseconds
            duration_milliseconds = $validationStopwatch.ElapsedMilliseconds
            child_pids = @($testModuleResults | ForEach-Object { $_.child_pid })
            termination_exit_code = $testTerminationExitCode
            termination_output = $testTerminationOutput
            module_results = @($testModuleResults)
            bootstrap_path = $testBootstrapPath
            bootstrap_sha256 = Get-Sha256 -Path $testBootstrapPath
            expected_package_path = Join-Path $repositoryRoot 'src\hive_mind_os\__init__.py'
            output_sha256 = Get-Sha256 -Path $testOutputPath
            stdout_sha256 = Get-Sha256 -Path $testStdoutPath
            stderr_sha256 = Get-Sha256 -Path $testStderrPath
            bytecode_paths_before = $bytecodeBefore
            bytecode_paths_after = $bytecodeAfter
        }
        external_gates = [ordered]@{
            independent_review = 'REQUIRED_NOT_SATISFIED'
            frozen_read_only_host = 'REQUIRED_NOT_SATISFIED'
            issuer_signature = 'REQUIRED_NOT_SATISFIED'
            nonce_compare_and_swap = 'REQUIRED_NOT_SATISFIED'
            protected_merge = 'NOT_AUTHORIZED'
            production_mutation = 'NOT_AUTHORIZED'
        }
    }
    Write-JsonFile -Path $evidencePath -Value $evidence

    $checksumsPath = Join-Path $OutputDirectory 'SHA256SUMS.txt'
    $checksumLines = @(
        "$(Get-Sha256 -Path $evidencePath)  evidence.json",
        "$(Get-Sha256 -Path $testOutputPath)  focused-test-output.txt",
        "$(Get-Sha256 -Path $testStdoutPath)  focused-test-stdout.txt",
        "$(Get-Sha256 -Path $testStderrPath)  focused-test-stderr.txt",
        "$(Get-Sha256 -Path $hostObservationPath)  host-observation.json",
        "$(Get-Sha256 -Path $reviewRequestPath)  independent-review-request.md",
        "$(Get-Sha256 -Path $testBootstrapPath)  focused-test-bootstrap.py",
        "$(Get-Sha256 -Path $templatePath)  unsigned-activation-template.json"
    )
    Write-Utf8File -Path $checksumsPath -Content ($checksumLines -join [Environment]::NewLine)

    if ($testTimedOut) {
        if ($testTimeoutScope -ceq 'module_process') {
            throw "Focused V4 validation exceeded a module deadline for $timedOutModule within the $FocusedTestTimeoutSeconds-second overall deadline; see $testOutputPath"
        }
        throw "Focused V4 validation exhausted the $FocusedTestTimeoutSeconds-second overall deadline before $deadlineExhaustedBeforeModule; see $testOutputPath"
    }
    if ($testExitCode -ne 0) {
        throw "Focused V4 validation failed; see $testOutputPath"
    }
    if (-not $planMatches -or -not $candidateBaseMatches -or -not $inertManifest) {
        throw "V4 artifact binding failed; see $evidencePath"
    }

    Write-Output "Evidence package created: $OutputDirectory"
    Write-Output "Qualification eligible: $qualificationEligible"
    Write-Output 'Activation authorized: False'
}
finally {
    if ($null -eq $previousPythonPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONPATH = $previousPythonPath
    }
    if ($null -eq $previousNoBytecode) {
        Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONDONTWRITEBYTECODE = $previousNoBytecode
    }
    foreach ($name in $inheritedGitEnvironment.Keys) {
        Set-Item -LiteralPath "Env:$name" -Value $inheritedGitEnvironment[$name]
    }
}
