@echo off
setlocal
cd /d "%~dp0"
echo ===== ROLLBACK -> 1.1.4 %DATE% %TIME% ===== > _rollback_out.txt
taskkill /IM dito_app.exe /F >> _rollback_out.txt 2>&1
taskkill /IM dito-engine.exe /F >> _rollback_out.txt 2>&1
timeout /t 2 >nul
start "" /wait "build\windows\installer\dito-1.1.4-setup.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
echo INSTALL_EXIT=%ERRORLEVEL% >> _rollback_out.txt
echo -- versao instalada -- >> _rollback_out.txt
powershell -command "(Get-Item \"$env:LOCALAPPDATA\Programs\Dito\dito_app.exe\").VersionInfo.FileVersion" >> _rollback_out.txt 2>&1
timeout /t 2 >nul
start "" "%LOCALAPPDATA%\Programs\Dito\dito_app.exe"
echo ROLLBACK_DONE >> _rollback_out.txt
endlocal
