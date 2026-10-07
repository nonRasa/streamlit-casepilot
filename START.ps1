$ErrorActionPreference = 'Stop'
if (-not $env:CASEPILOT_MODE) { $env:CASEPILOT_MODE = 'replay' }
if (-not $env:CASEPILOT_API_TOKEN) { $env:CASEPILOT_API_TOKEN = [guid]::NewGuid().ToString('N') }
if (-not $env:CASEPILOT_REVIEW_TOKEN) { $env:CASEPILOT_REVIEW_TOKEN = [guid]::NewGuid().ToString('N') }
Write-Host 'Local UI: http://127.0.0.1:8765'
Write-Host 'Copy the following local tokens into the matching UI fields:'
Write-Host ('Operator: ' + $env:CASEPILOT_API_TOKEN)
Write-Host ('Reviewer: ' + $env:CASEPILOT_REVIEW_TOKEN)
Write-Host 'Stop the server with Ctrl+C. Metis credentials never go in the browser.'
& (Join-Path $PSScriptRoot 'run.ps1') run.py serve
exit $LASTEXITCODE
