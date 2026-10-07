param([Parameter(ValueFromRemainingArguments = $true)][string[]]$PythonArgs)
$ErrorActionPreference = 'Stop'
$casepilotCandidates = @(
    (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
)
$casepilotInstalled = Get-Command python -ErrorAction SilentlyContinue
if ($casepilotInstalled -and $casepilotInstalled.Source -notlike '*WindowsApps*') {
    $casepilotCandidates += $casepilotInstalled.Source
}
$casepilotPython = $null
foreach ($casepilotCandidate in $casepilotCandidates) {
    if (Test-Path -LiteralPath $casepilotCandidate -PathType Leaf) {
        & $casepilotCandidate -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
        if ($LASTEXITCODE -eq 0) { $casepilotPython = $casepilotCandidate; break }
    }
}
if (-not $casepilotPython) { throw 'Python 3.11+ is required. Install it or create .venv in this folder.' }
if (-not $PythonArgs -or $PythonArgs.Count -eq 0) { $PythonArgs = @('run.py','doctor') }
Push-Location -LiteralPath $PSScriptRoot
try {
    & $casepilotPython -X utf8 @PythonArgs
    $casepilotExitCode = $LASTEXITCODE
} finally { Pop-Location }
exit $casepilotExitCode
