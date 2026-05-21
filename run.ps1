# Voice Flow — quick start (terminal mode with visible console)
# Usage: .\run.ps1            (default)
#        .\run.ps1 --verbose  (args are forwarded to voice-flow)

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if (-not (Test-Path ".venv")) {
    Write-Host "[setup] Creating virtual env (.venv) ..." -ForegroundColor Cyan
    python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1

if (-not (Test-Path ".env")) {
    Write-Host "[setup] .env missing — copying .env.example -> .env" -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host "[ATTENTION] Add OPENAI_API_KEY (and optional ANTHROPIC_API_KEY) to .env." -ForegroundColor Red
    notepad .env
    Write-Host "[setup] Save the file, then run .\run.ps1 again." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path ".venv\Scripts\voice-flow.exe")) {
    Write-Host "[setup] Installing voice-flow (pip install -e .) ..." -ForegroundColor Cyan
    pip install -e . 2>&1 | Out-Host
}

& voice-flow @args
