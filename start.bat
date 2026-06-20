@echo off
title DROPS LAN Server
cd /d "%~dp0"
chcp 65001 > nul

echo ====================================================
echo  DROPS LAN -- Сверхбыстрая передача файлов
echo ====================================================
echo.
python drops.py
echo.
echo Сервер остановлен.
pause
