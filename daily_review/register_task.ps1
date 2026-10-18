# Register a user-level Windows Task Scheduler job for 22:00 daily.
# Run this once in a normal PowerShell window. It does not need admin.
# Remove with: schtasks /Delete /TN "DSH-Daily-Review" /F

$ErrorActionPreference = 'Stop'
$taskName = 'DSH-Daily-Review'
$cmd = Join-Path $PSScriptRoot 'run_review.cmd'
if (-not (Test-Path -LiteralPath $cmd)) {
    throw "not found: $cmd"
}
$action = 'cmd.exe /c "' + $cmd + '"'
& schtasks.exe /Create /TN $taskName /TR $action /SC DAILY /ST 22:00 /RL LIMITED /F
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Registered: $taskName -> $cmd"
Write-Host "Check: schtasks /Query /TN $taskName /V /FO LIST"
