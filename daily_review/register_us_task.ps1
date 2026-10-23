# Register the US-market refresh task at 06:00 Beijing time.
# The main task (22:00) remains DSH-Daily-Review.
# Run this once in a normal PowerShell window. No admin required.
# Remove with: schtasks /Delete /TN "DSH-US-Review" /F

$ErrorActionPreference = 'Stop'
$taskName = 'DSH-US-Review'
$cmd = Join-Path $PSScriptRoot 'run_review.cmd'
if (-not (Test-Path -LiteralPath $cmd)) { throw "not found: $cmd" }
$action = 'cmd.exe /c "' + $cmd + '"'
& schtasks.exe /Create /TN $taskName /TR $action /SC DAILY /ST 06:00 /RL LIMITED /F
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Registered: $taskName -> $cmd (daily 06:00)"
Write-Host "Check: schtasks /Query /TN $taskName /V /FO LIST"
