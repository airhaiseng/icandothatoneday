param(
    [switch]$Quiet,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'review.py'
$logDir = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("review-{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))

# Pause switch: state/auto_review.json.  This is checked before Python or any
# network call, so a paused scheduled task costs nothing.
$statePath = Join-Path $PSScriptRoot 'state\auto_review.json'
$paused = $false
if (Test-Path -LiteralPath $statePath) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $paused = [bool]$state.paused
    } catch { $paused = $false }
}
if ($paused -and -not $Force) {
    $msg = "[review] paused by $statePath; skip. Use -Force to run once, or resume_auto_review.cmd."
    $msg | Out-File -FilePath $log -Encoding utf8 -Append
    if (-not $Quiet) { Write-Output $msg }
    exit 0
}

$candidates = @(
    'C:\Users\28704\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe',
    'python.exe'
)
$py = $null
foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) { $py = $candidate; break }
}
if (-not $py) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source }
}
if (-not $py) {
    Write-Error 'Python not found. Install Python 3.10+ or edit run_review.ps1.'
    exit 2
}

$env:PYTHONIOENCODING = 'utf-8'
$output = & $py $script 2>&1
$code = $LASTEXITCODE

$output | Out-File -FilePath $log -Encoding utf8 -Append
if (-not $Quiet) { $output | Write-Output }

# Rebuild the self-contained dashboard after every review.
$dashboard = Join-Path $PSScriptRoot 'build_dashboard.py'
if (Test-Path -LiteralPath $dashboard) {
    $dashOutput = & $py $dashboard 2>&1
    $dashCode = $LASTEXITCODE
    $dashOutput | Out-File -FilePath $log -Encoding utf8 -Append
    if (-not $Quiet) { $dashOutput | Write-Output }
    if ($code -eq 0 -and $dashCode -ne 0) { $code = 4 }
}

exit $code
