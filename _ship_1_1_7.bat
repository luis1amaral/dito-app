@echo off
REM ===== DITO 1.1.7 SHIP (VERIFICACAO): portao -> build engine+app -> instalador -> DESINSTALA/INSTALA LIMPO -> captura =====
REM SEM push aqui: o push e o _commit_1_1_7.bat, so depois do cartao.png ser conferido.
setlocal enabledelayedexpansion
cd /d "%~dp0"
set LOG=_ship_1_1_7.log
echo ===== DITO 1.1.7 SHIP %DATE% %TIME% ===== > "%LOG%"

set VER=1.1.7
set APPDIR=%LOCALAPPDATA%\Programs\Dito
set APPEXE=%APPDIR%\dito_app.exe
set SETUP=build\windows\installer\dito-%VER%-setup.exe
set SHOT=%~dp0_shot

REM --- 1) pub get ---
echo [1] flutter pub get >> "%LOG%"
call flutter pub get >> "%LOG%" 2>&1
echo PUBGET_EXIT=%ERRORLEVEL% >> "%LOG%"

REM --- 2) PORTAO: analyze ---
echo [2] flutter analyze >> "%LOG%"
call flutter analyze >> "%LOG%" 2>&1
set ANALYZE=%ERRORLEVEL%
echo ANALYZE_EXIT=%ANALYZE% >> "%LOG%"

REM --- 3) PORTAO: test ---
echo [3] flutter test >> "%LOG%"
call flutter test >> "%LOG%" 2>&1
set TESTS=%ERRORLEVEL%
echo TEST_EXIT=%TESTS% >> "%LOG%"

if not "%ANALYZE%"=="0" goto :gatefail
if not "%TESTS%"=="0" goto :gatefail

REM --- 4) build engine (PyInstaller console=False + UTF-8) + app + instalador Inno ---
echo [4] construir.ps1 (engine + app + inno) >> "%LOG%"
powershell -ExecutionPolicy Bypass -File packaging\windows\construir.ps1 -SemPortao >> "%LOG%" 2>&1
echo BUILD_EXIT=%ERRORLEVEL% >> "%LOG%"
if not exist "%SETUP%" (
  echo *** INSTALADOR NAO GERADO: %SETUP% *** >> "%LOG%"
  goto :end
)
echo -- SHA256SUMS -- >> "%LOG%"
type build\windows\installer\SHA256SUMS.txt >> "%LOG%" 2>&1

REM --- 5) DESINSTALACAO LIMPA ---
echo [5] desinstalacao limpa >> "%LOG%"
taskkill /IM dito_app.exe /F >> "%LOG%" 2>&1
taskkill /IM dito-engine.exe /F >> "%LOG%" 2>&1
timeout /t 2 >nul
if exist "%APPDIR%\unins000.exe" (
  echo rodando unins000.exe /VERYSILENT >> "%LOG%"
  start "" /wait "%APPDIR%\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
)
timeout /t 2 >nul
if exist "%APPDIR%" rmdir /s /q "%APPDIR%" >> "%LOG%" 2>&1
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Dito.lnk" >> "%LOG%" 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{8E3B5A2C-4D71-4C0E-9A6F-2F1D6B0A7E31}_is1" /f >> "%LOG%" 2>&1
if exist "%APPEXE%" ( echo AINDA_INSTALADO >> "%LOG%" ) else ( echo LIMPO_OK >> "%LOG%" )

REM --- 6) INSTALA DO ZERO (autostart on; pula download de modelos/gpu ja cacheados) ---
echo [6] instalando 1.1.7 do zero >> "%LOG%"
start "" /wait "%SETUP%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /MERGETASKS="startup,!model,!gpu,!desktopicon"
echo INSTALL_EXIT=%ERRORLEVEL% >> "%LOG%"
echo -- versao instalada -- >> "%LOG%"
powershell -command "(Get-Item \"%APPEXE%\").VersionInfo.FileVersion" >> "%LOG%" 2>&1
echo -- atalho de startup passa --startup? -- >> "%LOG%"
powershell -command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(\"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Dito.lnk\"); Write-Output ('TARGET=' + $s.TargetPath + ' ARGS=' + $s.Arguments)" >> "%LOG%" 2>&1

REM --- 7) CAPTURA HEADLESS (Gravando + cartao/Editar) para conferir o modal ---
echo [7] captura headless (HUD + cartao) >> "%LOG%"
if not exist "%SHOT%" mkdir "%SHOT%"
taskkill /IM dito_app.exe /F >> "%LOG%" 2>&1
taskkill /IM dito-engine.exe /F >> "%LOG%" 2>&1
timeout /t 2 >nul
set DITO_HUD_HOLD=1
set DITO_HUD_SHOT=%SHOT%
start "" "%APPEXE%"
timeout /t 60 >nul
set DITO_HUD_HOLD=
set DITO_HUD_SHOT=
taskkill /IM dito_app.exe /F >> "%LOG%" 2>&1
taskkill /IM dito-engine.exe /F >> "%LOG%" 2>&1
echo -- arquivos em _shot -- >> "%LOG%"
dir /b "%SHOT%" >> "%LOG%" 2>&1

echo SHIP_DONE_OK >> "%LOG%"
goto :end

:gatefail
echo *** PORTAO REPROVOU (analyze=%ANALYZE% test=%TESTS%): NAO BUILDEI/INSTALEI *** >> "%LOG%"
echo SHIP_ABORTED_GATE >> "%LOG%"

:end
echo ===== FIM %DATE% %TIME% ===== >> "%LOG%"
echo.
echo Log completo em %~dp0%LOG%
pause
endlocal
