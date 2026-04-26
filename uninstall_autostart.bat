@echo off
chcp 65001 >nul
title 自動起動の解除

REM Windowsスタートアップから「株式開示ダイジェスト」を解除します
powershell -NoProfile -Command "$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) '株式開示ダイジェスト.lnk'; if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host '削除完了: ' $lnk } else { Write-Host '登録されていません' }"

echo.
pause
