@echo off
setlocal
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is required to run PC Builder.
  pause
  exit /b 1
)

if not exist node_modules (
  echo Installing app dependencies...
  call npm install
  if errorlevel 1 (
    echo Dependency install failed.
    pause
    exit /b 1
  )
)

echo Starting PC Builder API on http://127.0.0.1:3001
start "PC Builder API" cmd /k "cd /d ""%~dp0"" && npm run server"

echo Starting PC Builder frontend on http://127.0.0.1:5173
start "PC Builder Frontend" cmd /k "cd /d ""%~dp0"" && npm run client"

timeout /t 2 >nul
start http://127.0.0.1:5173
endlocal
