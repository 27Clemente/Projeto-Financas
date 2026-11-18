@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Minhas Financas
echo.
echo   Iniciando Minhas Financas...
echo   Abra no navegador: http://127.0.0.1:3000
echo   Para encerrar, aperte Ctrl+C ou feche esta janela.
echo.
python server/app.py
echo.
echo   O servidor foi encerrado.
pause
