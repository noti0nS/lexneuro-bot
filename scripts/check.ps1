$ErrorActionPreference = "Stop"

Write-Host "=== ruff check ==="
.venv\Scripts\ruff.exe check .

Write-Host "=== ruff format (--check) ==="
.venv\Scripts\ruff.exe format --check .

Write-Host "=== basedpyright ==="
.venv\Scripts\python.exe -m basedpyright src tests

Write-Host "=== pytest ==="
.venv\Scripts\python.exe -m pytest
