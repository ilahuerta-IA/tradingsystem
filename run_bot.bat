@echo off
title Bot Trading Controller
cd C:\TradingBot

:loop
echo [%DATE% %TIME%] Iniciando Bot... >> crash_log.txt
:: Activamos el entorno y lanzamos el bot
call venv\Scripts\activate.bat
python run_multi_live.py

:: Si el bot se cierra (crash o error), llegamos aquí
echo [%DATE% %TIME%] !CRASH DETECTADO! Reiniciando en 10 segundos... >> crash_log.txt
echo ------------------------------------------------------------- >> crash_log.txt

:: Esperar 10 segundos antes de reintentar para no saturar CPU si el error es persistente
timeout /t 10

:: Volver al inicio (bucle infinito)
goto loop