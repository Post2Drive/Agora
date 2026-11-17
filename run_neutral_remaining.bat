@echo off
rem Neutral re-run of the remaining seven factorial conditions.
rem Keeps E0_C0_D0 (biased control) untouched. Run only when nothing else is running.
setlocal enabledelayedexpansion
cd /d %USERPROFILE%\Downloads\agora
call .venv\Scripts\activate.bat
if not exist ncc-factorial-150\logs mkdir ncc-factorial-150\logs

rem 1. Keep the biased population code and switch to the neutral code.
if not exist agora\sim\population.biased.py copy /y agora\sim\population.py agora\sim\population.biased.py >nul
copy /y agora\sim\population.neutral.py agora\sim\population.py >nul
echo Population code switched to neutral start.

rem 2. Run each remaining condition in turn.
for %%C in (E0_C0_D1 E0_C1_D0 E0_C1_D1 E1_C0_D0 E1_C0_D1 E1_C1_D0 E1_C1_D1) do (
  set "D=ncc-factorial-150\%%C"
  echo.
  echo ===== %%C  started %date% %time%
  if exist "!D!\agora.db" ren "!D!\agora.db" agora.db.biased-partial
  if exist "!D!\agora.db-wal" ren "!D!\agora.db-wal" agora.db-wal.biased-partial
  if exist "!D!\agora.db-shm" ren "!D!\agora.db-shm" agora.db-shm.biased-partial
  if not exist "!D!\scenario.biased.yaml" copy /y "!D!\scenario.yaml" "!D!\scenario.biased.yaml" >nul
  copy /y "!D!\scenario.neutral.yaml" "!D!\scenario.yaml" >nul
  agora run "!D!" > "ncc-factorial-150\logs\%%C-neutral.log" 2>&1
  echo ===== %%C finished %date% %time% exit !errorlevel!
)
echo.
echo ALL SEVEN NEUTRAL CONDITIONS DONE. Check with: agora status ncc-factorial-150\E0_C0_D1
pause
