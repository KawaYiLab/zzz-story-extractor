$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv ..."
    python -m venv .venv
}

Write-Host "Installing project ..."
.\.venv\Scripts\python.exe -m pip install -e .

Write-Host "Running doctor ..."
.\.venv\Scripts\python.exe -m zzz_story doctor

Write-Host ""
Write-Host "Setup complete. Run:"
Write-Host "  .\.venv\Scripts\python.exe -m zzz_story extract --out out"
