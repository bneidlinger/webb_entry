param([switch]$Sample)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$api = Join-Path $repo 'services/api'
$web = Join-Path $repo 'apps/web'
$python = Join-Path $api '.venv/Scripts/python.exe'
$node = (Get-Command node.exe -ErrorAction Stop).Source
$next = Join-Path $web 'node_modules/next/dist/bin/next'
$logs = Join-Path $repo 'logs'
if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $next)) {
    throw 'Install the API venv and web node_modules first; see docs/local-dev-without-docker.md.'
}
foreach ($port in @(8000, 3000)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Stop its service or use the existing instance."
    }
}
New-Item -ItemType Directory -Force -Path $logs | Out-Null
Push-Location $api
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    if ($Sample) {
        & $python -m app sample run --limit 3 --max-file-mib 16 --max-total-mib 32
        if ($LASTEXITCODE -ne 0) { throw 'Sample processing failed; inspect the JSON errors.' }
    }
} finally { Pop-Location }
$apiProcess = Start-Process -FilePath $python -ArgumentList @(
    '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'
) -WorkingDirectory $api -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $logs 'api.stdout.log') `
  -RedirectStandardError (Join-Path $logs 'api.stderr.log')
$webProcess = Start-Process -FilePath $node -ArgumentList @(
    $next, 'dev', '--hostname', '127.0.0.1', '--port', '3000'
) -WorkingDirectory $web -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput (Join-Path $logs 'web.stdout.log') `
  -RedirectStandardError (Join-Path $logs 'web.stderr.log')
@{ api = $apiProcess.Id; web = $webProcess.Id } | ConvertTo-Json | Set-Content (Join-Path $logs 'local-pids.json')
Write-Output "Web: http://localhost:3000 | API: http://localhost:8000/docs"
Write-Output "PIDs: API $($apiProcess.Id), web $($webProcess.Id). Logs: $logs"
