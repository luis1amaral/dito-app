@echo off
setlocal
cd /d "%~dp0"
set LOG=_ship_1_1_6.log
echo ===== DITO 1.1.6 SHIP %DATE% %TIME% ===== > "%LOG%"

del /f /q .git\index.lock .git\HEAD.lock 2>nul

REM --- 1) remover codigo morto (idempotente) ---
echo [1] removendo Spring >> "%LOG%"
git rm -f --ignore-unmatch lib/motion/spring.dart test/spring_test.dart >> "%LOG%" 2>&1
if exist lib\motion\spring.dart del /f /q lib\motion\spring.dart
if exist test\spring_test.dart del /f /q test\spring_test.dart

REM --- 2) pub get ---
echo [2] flutter pub get >> "%LOG%"
call flutter pub get >> "%LOG%" 2>&1
echo PUBGET_EXIT=%ERRORLEVEL% >> "%LOG%"

REM --- 3) PORTAO: analyze ---
echo [3] flutter analyze >> "%LOG%"
call flutter analyze >> "%LOG%" 2>&1
set ANALYZE=%ERRORLEVEL%
echo ANALYZE_EXIT=%ANALYZE% >> "%LOG%"

REM --- 4) PORTAO: test ---
echo [4] flutter test >> "%LOG%"
call flutter test >> "%LOG%" 2>&1
set TESTS=%ERRORLEVEL%
echo TEST_EXIT=%TESTS% >> "%LOG%"

if not "%ANALYZE%"=="0" goto :gatefail
if not "%TESTS%"=="0" goto :gatefail

REM --- 5) commit + push (so com portao verde) ---
echo [5] commit + push >> "%LOG%"
git add -A -- lib test pubspec.yaml pubspec.lock CHANGELOG.md docs >> "%LOG%" 2>&1
git -c user.name="Luis (Cowork)" -c user.email="lluispaulop@gmail.com" commit -m "[FIX]: readable review card; drop dead Spring code; add the Linux platform seam; bump 1.1.6" >> "%LOG%" 2>&1
echo COMMIT_EXIT=%ERRORLEVEL% >> "%LOG%"
git push origin master >> "%LOG%" 2>&1
echo PUSH_EXIT=%ERRORLEVEL% >> "%LOG%"
git rev-parse HEAD >> "%LOG%" 2>&1
git rev-parse origin/master >> "%LOG%" 2>&1

REM --- 6) build do instalador 1.1.6 ---
echo [6] construir instalador 1.1.6 >> "%LOG%"
powershell -ExecutionPolicy Bypass -File packaging\windows\construir.ps1 -SemPortao >> "%LOG%" 2>&1
echo BUILD_EXIT=%ERRORLEVEL% >> "%LOG%"
echo -- SHA256SUMS -- >> "%LOG%"
type build\windows\installer\SHA256SUMS.txt >> "%LOG%" 2>&1

REM --- 7) instalar silencioso (per-user, sem UAC) ---
echo [7] instalando 1.1.6 >> "%LOG%"
taskkill /IM dito_app.exe /F >> "%LOG%" 2>&1
taskkill /IM dito-engine.exe /F >> "%LOG%" 2>&1
timeout /t 2 >nul
start "" /wait "build\windows\installer\dito-1.1.6-setup.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
echo INSTALL_EXIT=%ERRORLEVEL% >> "%LOG%"
echo -- versao instalada -- >> "%LOG%"
powershell -command "(Get-Item \"$env:LOCALAPPDATA\Programs\Dito\dito_app.exe\").VersionInfo.FileVersion" >> "%LOG%" 2>&1

REM --- 8) captura headless do cartao (prova de contraste, sem computer-use) ---
echo [8] captura headless do cartao >> "%LOG%"
if not exist _shot mkdir _shot
taskkill /IM dito_app.exe /F >> "%LOG%" 2>&1
taskkill /IM dito-engine.exe /F >> "%LOG%" 2>&1
timeout /t 2 >nul
set DITO_HUD_HOLD=1
set DITO_HUD_SHOT=%~dp0_shot
start "" "%LOCALAPPDATA%\Programs\Dito\dito_app.exe"
timeout /t 50 >nul
set DITO_HUD_HOLD=
set DITO_HUD_SHOT=
echo -- arquivos em _shot -- >> "%LOG%"
dir /b _shot >> "%LOG%" 2>&1

REM --- 9) GitHub Release v1.1.6 + anexar o instalador ---
echo [9] GitHub Release v1.1.6 >> "%LOG%"
where gh >nul 2>&1
if errorlevel 1 (
  echo GH_MISSING: gh CLI nao encontrado no PATH >> "%LOG%"
  goto :releasedone
)
gh auth status >> "%LOG%" 2>&1
if errorlevel 1 (
  echo GH_MISSING: gh nao autenticado >> "%LOG%"
  goto :releasedone
)
gh release create v1.1.6 "build\windows\installer\dito-1.1.6-setup.exe" --repo luis1amaral/dito-flutter --title "Dito 1.1.6" --notes "Cartao de revisao legivel, limpeza de codigo morto e base para o Linux. Instalador Windows anexado." >> "%LOG%" 2>&1
echo RELEASE_EXIT=%ERRORLEVEL% >> "%LOG%"
echo -- URL da release -- >> "%LOG%"
gh release view v1.1.6 --repo luis1amaral/dito-flutter --json url -q .url >> "%LOG%" 2>&1
:releasedone

echo SHIP_DONE_OK >> "%LOG%"
goto :end

:gatefail
echo *** PORTAO REPROVOU (analyze=%ANALYZE% test=%TESTS%): NAO COMMITEI/PUSHEI/BUILDEI *** >> "%LOG%"
echo SHIP_ABORTED_GATE >> "%LOG%"

:end
echo ===== FIM ===== >> "%LOG%"
endlocal
