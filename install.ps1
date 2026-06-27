# Voice Flow - Installation auf Windows
#
# Was passiert:
#  1. Virtual-Env (.venv) anlegen falls fehlend
#  2. Package installieren (pip install -e .)
#  3. .env aus .env.example kopieren falls fehlend (notepad oeffnet sich)
#  4. Icon generieren (voice-flow.ico)
#  5. Desktop-Shortcut "Voice Flow" anlegen (pythonw.exe -m voice_flow, silent)
#  6. Startmenu-Eintrag anlegen
#  7. Frage: Autostart bei Windows-Login aktivieren?
#
# Usage:
#   .\install.ps1                # interaktiv
#   .\install.ps1 -Autostart     # ohne Frage Autostart aktivieren
#   .\install.ps1 -NoAutostart   # ohne Frage Autostart deaktiviert
#   .\install.ps1 -NoShortcut    # nur Setup, keine Shortcuts

param(
    [switch]$Autostart,
    [switch]$NoShortcut,
    [switch]$NoAutostart
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host " Voice Flow - Installation" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Virtual-Env ---
if (-not (Test-Path ".venv")) {
    Write-Host "[1/6] Erstelle Virtual-Env (.venv) ..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "[1/6] Virtual-Env bereits da. OK." -ForegroundColor Green
}

. .\.venv\Scripts\Activate.ps1

# --- 2. Package installieren ---
# Erkennen via CLI-Exe in .venv\Scripts (wird von [project.scripts] generiert)
$voiceFlowExe = Join-Path $projectRoot ".venv\Scripts\voice-flow.exe"
if (-not (Test-Path $voiceFlowExe)) {
    Write-Host "[2/6] Installiere voice-flow (pip install -e .) ..." -ForegroundColor Yellow
    # PowerShell behandelt stderr-Output von pip mit ErrorActionPreference=Stop als Exception,
    # auch wenn pip erfolgreich war. Lokal auf Continue stellen, ExitCode auswerten.
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & cmd.exe /c "pip install -e . 2>&1"
    $pipExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEAP
    if ($pipExit -ne 0) {
        Write-Host "FEHLER: pip install fehlgeschlagen (ExitCode $pipExit)" -ForegroundColor Red
        exit 1
    }
    if (-not (Test-Path $voiceFlowExe)) {
        Write-Host "FEHLER: voice-flow.exe nach pip install nicht gefunden" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[2/6] voice-flow bereits installiert. OK." -ForegroundColor Green
}

# --- 3. .env ---
if (-not (Test-Path ".env")) {
    Write-Host "[3/6] .env fehlt - kopiere .env.example -> .env" -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host ""
    Write-Host "  ACHTUNG: Notepad oeffnet jetzt .env." -ForegroundColor Red
    Write-Host "  Trage deinen OPENAI_API_KEY ein (Pflicht)." -ForegroundColor Red
    Write-Host "  Optional: ANTHROPIC_API_KEY (aktiviert Claude-Cleanup)." -ForegroundColor Red
    Write-Host "  Datei speichern und schliessen, dann laeuft Setup weiter." -ForegroundColor Red
    Write-Host ""
    Start-Process -FilePath notepad.exe -ArgumentList ".env" -Wait
} else {
    Write-Host "[3/6] .env bereits da. OK." -ForegroundColor Green
}

# --- 4. Icon generieren ---
# Regeneriere wenn .ico fehlt ODER logo.png neuer ist als .ico (Branding-Update)
$regen = $false
if (-not (Test-Path "voice-flow.ico")) {
    $regen = $true
} elseif (Test-Path "logo.png") {
    $logoMtime = (Get-Item "logo.png").LastWriteTime
    $icoMtime = (Get-Item "voice-flow.ico").LastWriteTime
    if ($logoMtime -gt $icoMtime) {
        Write-Host "[4/6] logo.png neuer als voice-flow.ico - regeneriere ..." -ForegroundColor Yellow
        $regen = $true
    }
}

if ($regen) {
    Write-Host "[4/6] Generiere voice-flow.ico ..." -ForegroundColor Yellow
    python make_icon.py
} else {
    Write-Host "[4/6] Icon bereits aktuell. OK." -ForegroundColor Green
}

if (Test-Path "logo.png") {
    Write-Host "       Logo:  logo.png gefunden - Galvanek-Branding aktiv" -ForegroundColor Green
} else {
    Write-Host "       Logo:  kein logo.png - Mikrofon-Fallback wird genutzt" -ForegroundColor Gray
    Write-Host "              Tipp: speichere dein Logo als logo.png in $projectRoot" -ForegroundColor Gray
}

if ($NoShortcut) {
    Write-Host ""
    Write-Host "Setup fertig (ohne Shortcuts wegen -NoShortcut)." -ForegroundColor Green
    Write-Host "Start: voice-flow  (in dieser PowerShell-Session)"
    exit 0
}

# --- 5. Shortcuts: Desktop + Startmenu ---
$pythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
# Shortcut-Icon: Root-.ico (von make_icon.py erzeugt) bevorzugen, sonst das
# gebundelte Package-Asset -> Desktop-Icon ist IMMER gebrandet, auch wenn
# make_icon.py mal scheitert.
$iconPath = Join-Path $projectRoot "voice-flow.ico"
if (-not (Test-Path $iconPath)) {
    $iconPath = Join-Path $projectRoot "src\voice_flow\assets\voice-flow.ico"
}

if (-not (Test-Path $pythonw)) {
    Write-Host "FEHLER: pythonw.exe nicht in .venv gefunden ($pythonw)" -ForegroundColor Red
    exit 1
}

function New-VoiceFlowShortcut {
    param([string]$Path, [string]$Description)
    $WshShell = New-Object -ComObject WScript.Shell
    $sc = $WshShell.CreateShortcut($Path)
    $sc.TargetPath = $pythonw
    $sc.Arguments = "-m voice_flow"
    $sc.WorkingDirectory = $projectRoot
    $sc.IconLocation = $iconPath
    $sc.Description = $Description
    $sc.WindowStyle = 7
    $sc.Save()
}

# Desktop
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Voice Flow.lnk"
New-VoiceFlowShortcut -Path $desktopShortcut -Description "Voice Flow - Push-to-Talk Diktat (F8 halten)"
Write-Host "[5/6] Desktop-Shortcut: $desktopShortcut" -ForegroundColor Green

# Startmenu
$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$startMenuShortcut = Join-Path $startMenuDir "Voice Flow.lnk"
New-VoiceFlowShortcut -Path $startMenuShortcut -Description "Voice Flow - Push-to-Talk Diktat (F8 halten)"
Write-Host "       Startmenu:        $startMenuShortcut" -ForegroundColor Green

# --- 6. Autostart ---
$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$startupShortcut = Join-Path $startupDir "Voice Flow.lnk"

$enableAutostart = $false
if ($Autostart) {
    $enableAutostart = $true
} elseif ($NoAutostart) {
    $enableAutostart = $false
} else {
    Write-Host ""
    $answer = Read-Host "[6/6] Autostart bei Windows-Login aktivieren? [J/n]"
    if ($answer -eq "" -or $answer -match "^[jJyY]") {
        $enableAutostart = $true
    }
}

if ($enableAutostart) {
    New-VoiceFlowShortcut -Path $startupShortcut -Description "Voice Flow - Autostart"
    Write-Host "       Autostart:        $startupShortcut" -ForegroundColor Green
} else {
    if (Test-Path $startupShortcut) {
        Remove-Item $startupShortcut
        Write-Host "       Autostart: entfernt" -ForegroundColor Yellow
    } else {
        Write-Host "       Autostart: aus" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host " Fertig!" -ForegroundColor Green
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Doppelklick auf  Voice Flow  (Desktop) zum Starten."
Write-Host "  F8 halten = Diktieren, Ctrl+Shift+Q = Beenden."
Write-Host "  Tray-Icon zeigt Status (grau=idle, rot=rec, orange=proc)."
Write-Host ""
Write-Host "  Deinstallieren: .\uninstall.ps1"
Write-Host ""
