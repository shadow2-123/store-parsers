@echo off
setlocal
cd /d "%~dp0"

set "CHROME_STEALTH=0"

if not exist ".venv\Scripts\python.exe" (
    echo Python environment not found. Run: uv sync
    pause
    exit /b 1
)

if not exist "logs" mkdir "logs"

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="%LOCALAPPDATA%\Chrome-Scraping"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$root = (Get-Location).Path; $python = Join-Path $root '.venv\Scripts\python.exe'; $services = @(@{Name='dns';Port=8101},@{Name='citilink';Port=8102},@{Name='onlinetrade';Port=8103}); foreach ($svc in $services) { $name = $svc.Name; $arguments = @('-m','uvicorn',($name + '.main:app'),'--host','127.0.0.1','--port',[string]$svc.Port); Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root ('logs\' + $name + '.out.log')) -RedirectStandardError (Join-Path $root ('logs\' + $name + '.err.log')); Write-Host ($name + ' started on port ' + $svc.Port) }"

if errorlevel 1 (
    echo Failed to start services. Check configuration.
    pause
    exit /b 1
)

exit /b 0
