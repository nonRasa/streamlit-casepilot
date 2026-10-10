# One small development-case run. The key is entered at a secure prompt,
# never passed as a command argument or written to this repository.
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = $env:CASEPILOT_PYTHON
if (-not $python) { $python = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $python) {
    $python = Get-Item -Path (Join-Path $env:USERPROFILE '.cache\*-runtimes\*-runtime\dependencies\python\python.exe') -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName -First 1
}
if (-not $python -or -not (Test-Path -LiteralPath $python)) { throw 'Set CASEPILOT_PYTHON to a Python interpreter with the project dependencies.' }

$secureKey = Read-Host -Prompt 'Metis key for one capped GH9218 run' -AsSecureString
try {
    $env:METIS_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
    $env:METIS_MODEL = 'gpt-4.1-mini'
    $env:METIS_BASE_URL = 'https://api.metisai.ir/openai/v1'
    $env:CASEPILOT_INPUT_USD_PER_MILLION = '0.44'
    $env:CASEPILOT_OUTPUT_USD_PER_MILLION = '1.76'
    $env:CASEPILOT_BUDGET_USD = '0.30'
    $env:CASEPILOT_BUDGET_DB = Join-Path $repoRoot 'runtime/v28_budget.sqlite3'
    $env:PYTHONIOENCODING = 'utf-8'
    Push-Location $repoRoot
    try {
        & $python scripts/run_single_live_v219.py --source-root . --output ../pair_live/v220_case_display_20261010 --label v220-case-display --incremental-cap-usd 0.025
        if ($LASTEXITCODE -ne 0) { throw "Live runner exited with code $LASTEXITCODE" }
    } finally { Pop-Location }
} finally {
    Remove-Item Env:METIS_API_KEY -ErrorAction SilentlyContinue
    Remove-Variable secureKey -ErrorAction SilentlyContinue
}
