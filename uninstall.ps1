# Voice Flow — remove shortcuts
#
# Removes Desktop, Start Menu, and autostart shortcuts.
# .venv and code stay — delete them yourself with Remove-Item -Recurse if you want.

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "Voice Flow — removing shortcuts" -ForegroundColor Cyan
Write-Host ""

$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "Voice Flow.lnk"
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Voice Flow.lnk"
$startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\Voice Flow.lnk"

foreach ($p in @($desktop, $startMenu, $startup)) {
    if (Test-Path $p) {
        Remove-Item $p
        Write-Host "  Removed: $p" -ForegroundColor Green
    } else {
        Write-Host "  Missing: $p" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Done. .venv and code are untouched." -ForegroundColor Green
Write-Host ""
