$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
& (Join-Path $project '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'test_native.py')
if ($LASTEXITCODE -ne 0) { throw 'Native portable smoke tests failed.' }
