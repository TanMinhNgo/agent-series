param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$env:RUN_RAG_INTEGRATION = "1"
& .\.venv\Scripts\python.exe -m pytest tests\test_rag_integration.py -m integration -q
exit $LASTEXITCODE
