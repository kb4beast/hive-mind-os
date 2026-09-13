$ErrorActionPreference = 'Stop'
. $env:HIVE_PROBE_RUNNER
$result = Invoke-BoundedPythonValidation -PythonExecutable $env:HIVE_PROBE_PYTHON -BootstrapPath $env:HIVE_PROBE_BOOTSTRAP -Modules @('tests.test_dag_executor') -WorkingDirectory $env:HIVE_PROBE_ROOT -TaskkillExecutable $env:HIVE_PROBE_TASKKILL -TimeoutMilliseconds 300000
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $env:HIVE_PROBE_RESULT
