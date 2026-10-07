$ErrorActionPreference = 'Stop'
if (-not $env:CASEPILOT_API_TOKEN) { $env:CASEPILOT_API_TOKEN = [guid]::NewGuid().ToString('N') }
if (-not $env:CASEPILOT_REVIEW_TOKEN) { $env:CASEPILOT_REVIEW_TOKEN = [guid]::NewGuid().ToString('N') }
Write-Host 'راهنما: کلید متیس در مرحلهٔ بعد با ورودی پنهان گرفته می‌شود؛ در مرورگر وارد نکنید.'
Write-Host ('توکن اپراتور: ' + $env:CASEPILOT_API_TOKEN)
Write-Host ('توکن بازبین: ' + $env:CASEPILOT_REVIEW_TOKEN)
Write-Host 'بودجه: سقف عملیاتی پیش‌فرض نیم دلار تجمعی است؛ دفتر هزینه را پاک نکنید.'
& (Join-Path $PSScriptRoot 'run.ps1') scripts/serve_live.py
exit $LASTEXITCODE
