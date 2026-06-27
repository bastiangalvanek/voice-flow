# Voice Flow - Shortcuts entfernen
#
# Entfernt Desktop, Startmenu und Autostart-Shortcuts.
# .venv und Code bleiben - die kannst du mit Remove-Item -Recurse selber loeschen.

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "Voice Flow - Shortcuts entfernen" -ForegroundColor Cyan
Write-Host ""

$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "Voice Flow.lnk"
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Voice Flow.lnk"
$startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\Voice Flow.lnk"

foreach ($p in @($desktop, $startMenu, $startup)) {
    if (Test-Path $p) {
        Remove-Item $p
        Write-Host "  Entfernt: $p" -ForegroundColor Green
    } else {
        Write-Host "  Nicht da: $p" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Fertig. .venv und Code bleiben unangetastet." -ForegroundColor Green
Write-Host ""
