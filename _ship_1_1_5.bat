@echo off
setlocal
cd /d "%~dp0"
set LOG=_ship_1_1_5.log
echo ===== DITO 1.1.5 SHIP %DATE% %TIME% ===== > "%LOG%"

REM --- limpar locks stale do git (deixados por tentativa no sandbox) ---
del /f /q .git\index.lock .git\HEAD.lock 2>nul

REM --- 1) remover codigo morto (Spring orfao) ---
echo [1] removendo Spring >> "%LOG%"
git rm -f lib/motion/spring.dart test/spring_test.dart >> "%LOG%" 2>&1
if exist lib\motion\spring.dart del /f /q lib\motion\spring.dart
if exist test\spring_test.dart del /f /q test\spring_test.dart

REM --- 2) pub get (pubspec mudou: sem 'path', arquivos novos) ---
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
git -c user.name="Luis (Cowork)" -c user.email="lluispaulop@gmail.com" commit -m "[CHORE]: drop dead Spring code, add the Linux platform seam, bump 1.1.5" >> "%LOG%" 2>&1
echo COMMIT_EXIT=%ERRORLEVEL% >> "%LOG%"
git push origin master >> "%LOG%" 2>&1
echo PUSH_EXIT=%ERRORLEVEL% >> "%LOG%"
git rev-parse HEAD >> "%LOG%" 2>&1
git rev-parse origin/master >> "%LOG%" 2>&1

REM --- 6) build do instalador 1.1.5 (portao ja rodou aqui) ---
echo [6] construir instalador 1.1.5 >> "%LOG%"
powershell -ExecutionPolicy Bypass -File packaging\windows\construir.ps1 -SemPortao >> "%LOG%" 2>&1
echo BUILD_EXIT=%ERRORLEVEL% >> "%LOG%"
echo -- SHA256SUMS -- >> "%LOG%"
type build\windows\installer\SHA256SUMS.txt >> "%LOG%" 2>&1

REM --- 7) instalar silencioso (per-user, sem UAC) e reabrir ---
echo [7] instalando 1.1.5 >> "%LOG%"
taskkill /IM dito_app.exe /F >> "%LOG%" 2>&1
taskkill /IM dito-engine.exe /F >> "%LOG%" 2>&1
timeout /t 2 >nul
start "" /wait "build\windows\installer\dito-1.1.5-setup.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
echo INSTALL_EXIT=%ERRORLEVEL% >> "%LOG%"
echo -- versao instalada -- >> "%LOG%"
powershell -command "(Get-Item \"$env:LOCALAPPDATA\Programs\Dito\dito_app.exe\").VersionInfo.FileVersion" >> "%LOG%" 2>&1
timeout /t 2 >nul
start "" "%LOCALAPPDATA%\Programs\Dito\dito_app.exe"
echo SHIP_DONE_OK >> "%LOG%"
goto :end

:gatefail
echo *** PORTAO REPROVOU (analyze=%ANALYZE% test=%TESTS%): NAO COMMITEI/PUSHEI/BUILDEI *** >> "%LOG%"
echo Veja os erros acima no proprio log. >> "%LOG%"
echo SHIP_ABORTED_GATE >> "%LOG%"

:end
echo ===== FIM ===== >> "%LOG%"
endlocal
