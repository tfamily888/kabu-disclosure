@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 株式開示ダイジェスト 自動起動

REM ============================================
REM  PC起動時に実行される自動起動スクリプト
REM    1. 古いサーバープロセスを停止
REM    2. データ取得（バックグラウンド）
REM    3. サーバー起動 + ブラウザ自動オープン
REM ============================================

REM Clear stale port file
if exist "%~dp0current_port.txt" del /f /q "%~dp0current_port.txt" >nul 2>&1

REM Kill any existing server processes on common ports (except System process)
powershell -NoProfile -Command "$ports = @(7777,7778,7779,7780,5500,8800); foreach ($p in $ports) { try { $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue; if ($c -and $c.OwningProcess -gt 4) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } } catch {} }" >nul 2>&1

timeout /t 2 /nobreak >nul

REM Ensure BOM on critical files
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0addbom.ps1" >nul 2>&1

REM Pre-fetch disclosure data (background, ~30s) - updates data/disclosures.json
start "" /B powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0fetch_disclosures.ps1" >nul 2>&1

REM Browser opener: waits for port file then opens browser
start "" /B powershell -NoProfile -WindowStyle Hidden -Command "$pf = '%~dp0current_port.txt'; for ($i=0; $i -lt 30; $i++) { if (Test-Path $pf) { $port = (Get-Content $pf -Raw).Trim(); if ($port) { Start-Process \"http://localhost:$port/\"; break } }; Start-Sleep -Milliseconds 500 }"

REM Start the server (blocks until server stops)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0server.ps1"
