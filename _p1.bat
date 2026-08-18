@echo off
cd /d "%~dp0"
del /f /q .git\index.lock .git\HEAD.lock 2>nul
del /f /q lib\motion\spring.dart test\spring_test.dart 2>nul
echo P1_START > _p1_out.txt
if exist lib\motion\spring.dart (echo spring.dart STILL EXISTS >> _p1_out.txt) else (echo spring.dart removed >> _p1_out.txt)
if exist test\spring_test.dart (echo spring_test.dart STILL EXISTS >> _p1_out.txt) else (echo spring_test.dart removed >> _p1_out.txt)
call flutter pub get >> _p1_out.txt 2>&1
echo PUBGET_EXIT=%ERRORLEVEL% >> _p1_out.txt
call flutter analyze >> _p1_out.txt 2>&1
echo ANALYZE_EXIT=%ERRORLEVEL% >> _p1_out.txt
call flutter test >> _p1_out.txt 2>&1
echo TEST_EXIT=%ERRORLEVEL% >> _p1_out.txt
echo P1_DONE >> _p1_out.txt
