$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& ./.venv/Scripts/python.exe tools/build_native.py
if ($LASTEXITCODE -ne 0) { throw 'Portable build failed.' }
Write-Host 'Native WebView2 portable executable is in dist/.'
