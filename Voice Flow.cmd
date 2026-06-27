@echo off
title Voice Flow
rem  EIN Klick: laufende Instanz beenden (falls vorhanden) + frisch starten.
rem  Beenden im Betrieb: das Voice-Flow-Fenster schliessen (X) oder "Voice Flow beenden".
rem  %~dp0 = Ordner dieser .cmd -> laeuft auf JEDEM PC, egal wohin entpackt.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { ($_.ExecutablePath -like '*\voice-flow\.venv\*') -or ($_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -match '-m\s+voice_flow') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
powershell -NoProfile -Command "Start-Sleep -Milliseconds 1000"
start "" ".venv\Scripts\pythonw.exe" -m voice_flow
