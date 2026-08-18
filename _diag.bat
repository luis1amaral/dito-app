@echo off
setlocal
cd /d "%~dp0"
if not exist _diag mkdir _diag
set L=%LOCALAPPDATA%\dito\logs
echo ===== DIAG %DATE% %TIME% ===== > _diag\diag.txt
echo -- pasta de logs: %L% -- >> _diag\diag.txt
dir /b "%L%" >> _diag\diag.txt 2>&1
echo -- copiando *.log -- >> _diag\diag.txt
copy /y "%L%\*.log" _diag\ >> _diag\diag.txt 2>&1
echo -- engine instalado? -- >> _diag\diag.txt
dir "%LOCALAPPDATA%\Programs\Dito\dito-engine\dito-engine.exe" >> _diag\diag.txt 2>&1
echo -- versao app -- >> _diag\diag.txt
powershell -command "(Get-Item \"$env:LOCALAPPDATA\Programs\Dito\dito_app.exe\").VersionInfo.FileVersion" >> _diag\diag.txt 2>&1
echo -- rodar o engine sozinho (deve responder engine_ready no stdout) -- >> _diag\diag.txt
echo {"cmd":"ping"} | "%LOCALAPPDATA%\Programs\Dito\dito-engine\dito-engine.exe" engine > _diag\engine_stdout.txt 2>_diag\engine_stderr.txt
echo ENGINE_RUN_EXIT=%ERRORLEVEL% >> _diag\diag.txt
echo DIAG_DONE >> _diag\diag.txt
endlocal
