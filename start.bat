@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 株式開示ダイジェスト サーバー

echo ============================================
echo  株式開示ダイジェスト サーバー起動中...
echo ============================================
echo.

REM Clear stale port file
if exist "%~dp0current_port.txt" del /f /q "%~dp0current_port.txt" >nul 2>&1

REM Kill any existing server processes on common ports (except System process)
echo [1/3] 古いサーバープロセスを停止中...
powershell -NoProfile -Command "$ports = @(7777,7778,7779,7780,5500,8800); foreach ($p in $ports) { try { $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue; if ($c -and $c.OwningProcess -gt 4) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } } catch {} }"

timeout /t 2 /nobreak >nul

REM Ensure BOM on critical files (needed after git/editor operations)
echo [2/3] 設定ファイルを準備中...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0addbom.ps1" >nul 2>&1

echo [3/3] サーバー起動中...
echo.

REM Start browser opener in background - it waits for port file then opens browser
start "" /B powershell -NoProfile -WindowStyle Hidden -Command "$pf = '%~dp0current_port.txt'; for ($i=0; $i -lt 30; $i++) { if (Test-Path $pf) { $port = (Get-Content $pf -Raw).Trim(); if ($port) { Start-Process \"http://localhost:$port/\"; break } }; Start-Sleep -Milliseconds 500 }"

REM Start the server (blocks until server stops)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0server.ps1"

echo.
echo サーバーが停止しました。
pause
