# Start the local dashboard with working pause/resume switch.
# Requires Python 3.10+. Bound to 127.0.0.1 only.

$ErrorActionPreference = 'Stop'
$py = $null
foreach ($candidate in @(
    'C:\Users\28704\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe',
    'python.exe'
)) {
    if (Test-Path -LiteralPath $candidate) { $py = $candidate; break }
}
if (-not $py) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source }
}
if (-not $py) { throw 'Python not found' }
& $py (Join-Path $PSScriptRoot 'control_server.py') --port 8777
