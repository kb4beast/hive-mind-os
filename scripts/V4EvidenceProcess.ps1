function Invoke-BoundedPythonValidation {
    param(
        [Parameter(Mandatory = $true)][string]$PythonExecutable,
        [Parameter(Mandatory = $true)][string]$BootstrapPath,
        [Parameter(Mandatory = $true)][string[]]$Modules,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$TaskkillExecutable,
        [Parameter(Mandatory = $true)][ValidateRange(1, 60000)][int]$TimeoutMilliseconds
    )

    if ($BootstrapPath.Contains('"')) {
        throw 'Focused-test bootstrap path contains an unsupported quote.'
    }
    foreach ($module in $Modules) {
        if ($module -notmatch '^tests\.[A-Za-z0-9_.]+$') {
            throw "Focused-test module name is not canonical: $module"
        }
    }

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $PythonExecutable
    $startInfo.Arguments = (
        '-I -B -X utf8 -W error::ResourceWarning "' +
        $BootstrapPath + '" -v ' + ($Modules -join ' ')
    )
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $removedPythonEnvironmentNames = @(
        @($startInfo.EnvironmentVariables.Keys) |
            Where-Object { $_.ToString().StartsWith('PYTHON', [System.StringComparison]::OrdinalIgnoreCase) } |
            ForEach-Object { $_.ToString() } |
            Sort-Object
    )
    foreach ($name in $removedPythonEnvironmentNames) {
        $startInfo.EnvironmentVariables.Remove($name)
    }
    $sourceRoot = Join-Path $WorkingDirectory 'src'
    $childPythonPath = $sourceRoot + [System.IO.Path]::PathSeparator + $WorkingDirectory
    $startInfo.EnvironmentVariables['PYTHONPATH'] = $childPythonPath
    $startInfo.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
    $startInfo.EnvironmentVariables['PYTHONUTF8'] = '1'

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        if (-not $process.Start()) {
            throw 'Focused-test process did not start.'
        }
        $childPid = $process.Id
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $terminationExitCode = $null
        $terminationOutput = @()
        $timedOut = -not $process.WaitForExit($TimeoutMilliseconds)
        if ($timedOut) {
            $savedErrorActionPreference = $ErrorActionPreference
            try {
                # Windows can report a child as already gone while taskkill is
                # walking the requested tree.  Capture that diagnostic and
                # decide from the exact spawned process state below instead of
                # allowing native stderr to become a terminating PowerShell
                # error under the collector's Stop policy.
                $ErrorActionPreference = 'Continue'
                $rawTerminationOutput = @(
                    & $TaskkillExecutable /PID $childPid /T /F 2>&1
                )
                $terminationExitCode = $LASTEXITCODE
                $terminationOutput = @(
                    $rawTerminationOutput | ForEach-Object { $_.ToString() }
                )
            }
            finally {
                $ErrorActionPreference = $savedErrorActionPreference
            }
            if (-not $process.WaitForExit(10000)) {
                throw "Focused-test process tree did not terminate after taskkill: $($terminationOutput -join '; ')"
            }
            if ($terminationExitCode -ne 0 -and -not $process.HasExited) {
                throw "Focused-test process-tree termination failed: $($terminationOutput -join '; ')"
            }
        }
        else {
            $process.WaitForExit()
        }
        if (-not [System.Threading.Tasks.Task]::WaitAll(
            [System.Threading.Tasks.Task[]]@($stdoutTask, $stderrTask),
            10000
        )) {
            throw 'Focused-test output streams did not close after process exit.'
        }
        $actualExitCode = $process.ExitCode
        $effectiveExitCode = if ($timedOut) { 124 } else { $actualExitCode }
        return [pscustomobject]@{
            stdout = $stdoutTask.Result
            stderr = $stderrTask.Result
            child_pid = $childPid
            timed_out = $timedOut
            timeout_seconds = $TimeoutMilliseconds / 1000.0
            timeout_milliseconds = $TimeoutMilliseconds
            duration_milliseconds = $stopwatch.ElapsedMilliseconds
            actual_exit_code = $actualExitCode
            effective_exit_code = $effectiveExitCode
            termination_exit_code = $terminationExitCode
            termination_output = $terminationOutput
            removed_python_environment_names = $removedPythonEnvironmentNames
            child_pythonpath = $childPythonPath
        }
    }
    finally {
        $stopwatch.Stop()
        $process.Dispose()
    }
}

function Get-V4UnittestTerminalResult {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Stdout,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Stderr,
        [Parameter(Mandatory = $true)][string]$Marker,
        [Parameter(Mandatory = $true)][ValidateRange(1, 1000000)][int]$ExpectedTestsRun
    )

    if ($Marker -notmatch '^HIVE_V4_UNITTEST_RESULT_[0-9a-f]{32}$') {
        throw 'Focused-test terminal marker is not canonical.'
    }
    $matches = [regex]::Matches(
        $Stdout,
        (
            '(?m)^' + [regex]::Escape($Marker) +
            ' tests_run=(?<tests_run>\d+)' +
            ' failures=(?<failures>\d+)' +
            ' errors=(?<errors>\d+)' +
            ' skipped=(?<skipped>\d+)' +
            ' expected_failures=(?<expected_failures>\d+)' +
            ' unexpected_successes=(?<unexpected_successes>\d+)' +
            ' successful=(?<successful>true|false)\r?$'
        )
    )
    $values = [ordered]@{
        tests_run = 0
        failures = 0
        errors = 0
        skipped = 0
        expected_failures = 0
        unexpected_successes = 0
        successful = $false
    }
    if ($matches.Count -eq 1) {
        foreach ($name in @(
            'tests_run',
            'failures',
            'errors',
            'skipped',
            'expected_failures',
            'unexpected_successes'
        )) {
            $values[$name] = [int]$matches[0].Groups[$name].Value
        }
        $values.successful = $matches[0].Groups['successful'].Value -ceq 'true'
    }
    $countMatches = $values.tests_run -eq $ExpectedTestsRun
    # ResourceWarning exceptions raised by -W error can be routed through
    # sys.unraisablehook during finalization.  Python then exits zero even though
    # stderr contains both the warning and an "Exception ignored" diagnostic.
    # Validate the fully drained stderr transcript instead of trusting only the
    # unittest result and child exit code.
    $resourceWarningStderrOccurrenceCount = (
        [regex]::Matches($Stderr, 'ResourceWarning:').Count
    )
    $unraisableExceptionStderrOccurrenceCount = (
        [regex]::Matches($Stderr, 'Exception ignored').Count
    )
    $outcomesClean = (
        $values.failures -eq 0 -and
        $values.errors -eq 0 -and
        $values.skipped -eq 0 -and
        $values.expected_failures -eq 0 -and
        $values.unexpected_successes -eq 0 -and
        $resourceWarningStderrOccurrenceCount -eq 0 -and
        $unraisableExceptionStderrOccurrenceCount -eq 0
    )
    return [pscustomobject][ordered]@{
        marker_count = $matches.Count
        tests_run = $values.tests_run
        expected_tests_run = $ExpectedTestsRun
        test_count_matches_expected = $countMatches
        failures = $values.failures
        errors = $values.errors
        skipped = $values.skipped
        expected_failures = $values.expected_failures
        unexpected_successes = $values.unexpected_successes
        resource_warning_stderr_occurrence_count = $resourceWarningStderrOccurrenceCount
        unraisable_exception_stderr_occurrence_count = (
            $unraisableExceptionStderrOccurrenceCount
        )
        successful = $values.successful
        outcomes_clean = $outcomesClean
        valid = (
            $matches.Count -eq 1 -and
            $values.successful -and
            $countMatches -and
            $outcomesClean
        )
    }
}
