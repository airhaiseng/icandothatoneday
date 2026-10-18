param(
    [ValidateSet('status', 'pause', 'resume')]
    [string]$Action = 'status',
    [switch]$NoRebuild
)

$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$stateDir = Join-Path $root 'state'
$statePath = Join-Path $stateDir 'auto_review.json'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

if ($Action -ne 'status') {
    $paused = $Action -eq 'pause'
    $obj = [ordered]@{
        paused    = $paused
        updatedAt = (Get-Date).ToString('o')
        reason    = if ($paused) { 'paused by control_auto_review.ps1' } else { 'resumed by control_auto_review.ps1' }
    }
    $obj | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
    Write-Host ("Auto review: " + ($(if ($paused) { 'PAUSED' } else { 'RUNNING' })))
} else {
    $paused = $false
    if (Test-Path -LiteralPath $statePath) {
        try { $paused = [bool](Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json).paused } catch {}
    }
    Write-Host ("Auto review: " + ($(if ($paused) { 'PAUSED' } else { 'RUNNING' })))
}

# Disable/enable the optional Windows scheduled task. DSH's built-in scheduled
# reminder is not controllable from a file; it was removed separately.
$taskName = 'DSH-Daily-Review'
$taskQuery = & schtasks.exe /Query /TN $taskName 2>$null
$taskExists = ($LASTEXITCODE -eq 0)
if ($taskExists -and $Action -ne 'status') {
    if ($Action -eq 'pause') {
        & schtasks.exe /Change /TN $taskName /DISABLE 2>$null | Out-Null
        Write-Host "Windows task '$taskName' disabled."
    } else {
        & schtasks.exe /Change /TN $taskName /ENABLE 2>$null | Out-Null
        Write-Host "Windows task '$taskName' enabled."
    }
} elseif (-not $taskExists) {
    Write-Host "Windows task '$taskName' not found (optional)."
}

# Repaint the local dashboard status badge without a network call.
if ($Action -ne 'status' -and -not $NoRebuild) {
    $candidates = @(
        'C:\Users\28704\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe',
        'python.exe'
    )
    $py = $null
    foreach ($candidate in $candidates) { if (Test-Path -LiteralPath $candidate) { $py = $candidate; break } }
    if (-not $py) { $cmd = Get-Command python -ErrorAction SilentlyContinue; if ($cmd) { $py = $cmd.Source } }
    $builder = Join-Path $root 'build_dashboard.py'
    if ($py -and (Test-Path -LiteralPath $builder)) {
        & $py $builder --offline 2>&1 | ForEach-Object { if ($_ -match '^\[dashboard\]') { Write-Host $_ } }
    }
}

if ($Action -eq 'status') {
    Write-Host "State file: $statePath"
}
