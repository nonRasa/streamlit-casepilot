$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" -X utf8 "$PSScriptRoot\scripts\evaluate_quality_v22_live.py" --live
exit $LASTEXITCODE
