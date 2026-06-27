# Voice Flow - Quick-Start fuer Windows (Terminal-Mode mit sichtbarer Konsole)
# Usage: .\run.ps1            (Standard-Modus)
#        .\run.ps1 --verbose  (Args werden an voice-flow weitergereicht)

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if (-not (Test-Path ".venv")) {
    Write-Host "[setup] Erstelle Virtual-Env (.venv) ..." -ForegroundColor Cyan
    python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1

if (-not (Test-Path ".env")) {
    Write-Host "[setup] .env fehlt - kopiere .env.example -> .env" -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host "[ACHTUNG] Bitte OPENAI_API_KEY (und optional ANTHROPIC_API_KEY) in .env eintragen." -ForegroundColor Red
    notepad .env
    Write-Host "[setup] Speichern, dann erneut .\run.ps1 starten." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path ".venv\Scripts\voice-flow.exe")) {
    Write-Host "[setup] Installiere voice-flow (pip install -e .) ..." -ForegroundColor Cyan
    pip install -e . 2>&1 | Out-Host
}

& voice-flow @args
