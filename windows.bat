@echo off
title Juego - Vida Pygame Zero

echo Verificando si pgzrun esta instalado...

python -m pip show pgzero >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo pgzero NO esta instalado. Instalando ahora...
    python -m pip install pgzero
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: No se pudo instalar pgzero.
        echo Intenta ejecutar este archivo como administrador.
        pause
        exit /b 1
    )
    echo pgzero instalado correctamente.
) else (
    echo pgzero ya esta instalado.
)

echo.
echo Iniciando el juego...
echo.

python -m pgzero vida.py

echo.
echo Juego finalizado.
pause
