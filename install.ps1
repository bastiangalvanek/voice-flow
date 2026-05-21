# Voice Flow — Windows installation
#
# What this does:
#  1. Create a virtual env (.venv) if missing
#  2. Install the package (pip install -e .)
#  3. Copy .env from .env.example if missing (Notepad opens)
#  4. Generate voice-flow.ico (uses logo.png if present, else mic fallback)
#  5. Create Desktop shortcut "Voice Flow"
#  6. Create Start Menu entry
#  7. Ask: enable autostart on Windows login?
#
# Usage:
#   .\install.ps1                # interactive
#   .\install.ps1 -Autostart     # enable autostart without prompt
#   .\install.ps1 -NoAutostart   # disable autostart without prompt
#   .\install.ps1 -NoShortcut    # setup only, no shortcuts

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
Write-Host " Voice Flow — Installation" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Virtual env ---
if (-not (Test-Path ".venv")) {
    Write-Host "[1/6] Creating virtual env (.venv) ..." -ForegroundColor Yellow
    python -m venv .venv
} else {
    Write-Host "[1/6] Virtual env already exists. OK." -ForegroundColor Green
}

. .\.venv\Scripts\Activate.ps1

# --- 2. Install package ---
$voiceFlowExe = Join-Path $projectRoot ".venv\Scripts\voice-flow.exe"
if (-not (Test-Path $voiceFlowExe)) {
    Write-Host "[2/6] Installing voice-flow (pip install -e .) ..." -ForegroundColor Yellow
    # pip writes to stderr even on success; ignore EAP=Stop for this call and check exit code.
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & cmd.exe /c "pip install -e . 2>&1"
    $pipExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEAP
    if ($pipExit -ne 0) {
        Write-Host "ERROR: pip install failed (exit $pipExit)" -ForegroundColor Red
        exit 1
    }
    if (-not (Test-Path $voiceFlowExe)) {
        Write-Host "ERROR: voice-flow.exe not found after pip install" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[2/6] voice-flow already installed. OK." -ForegroundColor Green
}

# --- 3. .env ---
if (-not (Test-Path ".env")) {
    Write-Host "[3/6] .env missing — copying .env.example -> .env" -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host ""
    Write-Host "  ATTENTION: Notepad is opening .env." -ForegroundColor Red
    Write-Host "  Paste your OPENAI_API_KEY (required)." -ForegroundColor Red
    Write-Host "  Optional: ANTHROPIC_API_KEY (enables Claude cleanup)." -ForegroundColor Red
    Write-Host "  Save and close the file to continue setup." -ForegroundColor Red
    Write-Host ""
    Start-Process -FilePath notepad.exe -ArgumentList ".env" -Wait
} else {
    Write-Host "[3/6] .env already exists. OK." -ForegroundColor Green
}

# --- 4. Generate icon ---
$regen = $false
if (-not (Test-Path "voice-flow.ico")) {
    $regen = $true
} elseif (Test-Path "logo.png") {
    $logoMtime = (Get-Item "logo.png").LastWriteTime
    $icoMtime = (Get-Item "voice-flow.ico").LastWriteTime
    if ($logoMtime -gt $icoMtime) {
        Write-Host "[4/6] logo.png newer than voice-flow.ico — regenerating ..." -ForegroundColor Yellow
        $regen = $true
    }
}

if ($regen) {
    Write-Host "[4/6] Generating voice-flow.ico ..." -ForegroundColor Yellow
    python make_icon.py
} else {
    Write-Host "[4/6] Icon already current. OK." -ForegroundColor Green
}

if (Test-Path "logo.png") {
    Write-Host "       Logo:  using logo.png" -ForegroundColor Green
} else {
    Write-Host "       Logo:  no logo.png — microphone fallback" -ForegroundColor Gray
    Write-Host "              Tip: save your logo as logo.png in $projectRoot" -ForegroundColor Gray
}

if ($NoShortcut) {
    Write-Host ""
    Write-Host "Setup done (no shortcuts, -NoShortcut was set)." -ForegroundColor Green
    Write-Host "Start: voice-flow  (in this PowerShell session)"
    exit 0
}

# --- 5. Shortcuts: Desktop + Start Menu ---
$pythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
$iconPath = Join-Path $projectRoot "voice-flow.ico"

if (-not (Test-Path $pythonw)) {
    Write-Host "ERROR: pythonw.exe not found in .venv ($pythonw)" -ForegroundColor Red
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

$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Voice Flow.lnk"
New-VoiceFlowShortcut -Path $desktopShortcut -Description "Voice Flow — push-to-talk dictation (hold F8)"
Write-Host "[5/6] Desktop shortcut: $desktopShortcut" -ForegroundColor Green

$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$startMenuShortcut = Join-Path $startMenuDir "Voice Flow.lnk"
New-VoiceFlowShortcut -Path $startMenuShortcut -Description "Voice Flow — push-to-talk dictation (hold F8)"
Write-Host "       Start Menu:       $startMenuShortcut" -ForegroundColor Green

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
    $answer = Read-Host "[6/6] Enable autostart on Windows login? [Y/n]"
    if ($answer -eq "" -or $answer -match "^[yYjJ]") {
        $enableAutostart = $true
    }
}

if ($enableAutostart) {
    New-VoiceFlowShortcut -Path $startupShortcut -Description "Voice Flow — autostart"
    Write-Host "       Autostart:        $startupShortcut" -ForegroundColor Green
} else {
    if (Test-Path $startupShortcut) {
        Remove-Item $startupShortcut
        Write-Host "       Autostart: removed" -ForegroundColor Yellow
    } else {
        Write-Host "       Autostart: off" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host " Done." -ForegroundColor Green
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Double-click  Voice Flow  (Desktop) to start."
Write-Host "  Hold F8 = dictate, Ctrl+Shift+Alt+Q = quit."
Write-Host "  Tray icon shows status (grey=idle, red=rec, orange=processing)."
Write-Host ""
Write-Host "  Uninstall: .\uninstall.ps1"
Write-Host ""
