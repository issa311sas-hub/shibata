param([Parameter(Mandatory)][string]$Python,
      [Parameter(Mandatory)][string]$EnvironmentDirectory,
      [Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
if ((Test-Path -LiteralPath $EnvironmentDirectory) -or (Test-Path -LiteralPath $OutputDirectory)) {
    throw 'Use new environment and output directories'
}
if (-not (Test-Path -LiteralPath 'requirements-phase0-lock.txt')) { throw 'Run from the repository root' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$taskPython=[IO.Path]::GetFullPath($Python)
$envDir=[IO.Path]::GetFullPath($EnvironmentDirectory)
$reportDir=[IO.Path]::GetFullPath($OutputDirectory)
$status=[ordered]@{status='RUNNING';scope='Phase 0 clean environment';started_at=[DateTimeOffset]::UtcNow.ToString('o');environment=$envDir}
try {
    & $taskPython -m venv $envDir
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
    $freshPython=Join-Path $envDir 'Scripts/python.exe'
    & $freshPython -m pip install -r requirements-phase0-lock.txt *> (Join-Path $reportDir 'install.log')
    if ($LASTEXITCODE -ne 0) { throw 'Locked dependency install failed; see install.log' }
    & $freshPython -m pip install --no-build-isolation --no-deps -e . *> (Join-Path $reportDir 'project-install.log')
    if ($LASTEXITCODE -ne 0) { throw 'Project install failed; see project-install.log' }
    & $freshPython -m pip check *> (Join-Path $reportDir 'pip-check.log')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed' }
    $junitPath=Join-Path $reportDir 'pytest.xml'
    $pytestTemp=Join-Path $reportDir 'pytest-temp'
    $pytestCache=Join-Path $reportDir 'pytest-cache'
    & $freshPython -m pytest -q "--junitxml=$junitPath" "--basetemp=$pytestTemp" -o "cache_dir=$pytestCache" *> (Join-Path $reportDir 'pytest.log')
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed; see pytest.log' }
    & $freshPython -m shibata.phase0_completion --output (Join-Path $reportDir 'acceptance') *> (Join-Path $reportDir 'acceptance.log')
    if ($LASTEXITCODE -ne 0) { throw 'Acceptance run failed; see acceptance.log' }
    $status.status='PASS'
} catch { $status.status='FAILED';$status.error=$_.Exception.Message }
finally {
    $status.finished_at=[DateTimeOffset]::UtcNow.ToString('o')
    $status.requirements_sha256=(Get-FileHash requirements-phase0-lock.txt -Algorithm SHA256).Hash.ToLowerInvariant()
    $status | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $reportDir 'clean-environment.json') -Encoding utf8
    $status | ConvertTo-Json
}
if ($status.status -ne 'PASS') { exit 1 }
