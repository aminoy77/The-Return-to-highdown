#!/usr/bin/env bash

echo "Verificando si pgzero está instalado..."

if ! python3 -m pip show pgzero &> /dev/null; then
    echo "pgzero NO está instalado → instalando ahora..."
    python3 -m pip install --user pgzero
    
    if [ $? -ne 0 ]; then
        echo "Error: no se pudo instalar pgzero"
        echo "Prueba ejecutando con sudo o revisa tu entorno python"
        read -p "Presiona Enter para salir..."
        exit 1
    fi
    
    echo "pgzero instalado correctamente"
else
    echo "pgzero ya está instalado"
fi

echo ""
echo "Iniciando el juego..."
echo "------------------------"
echo ""

python3 -m pgzero vida.py

echo ""
echo "Juego terminado."
read -p "Presiona Enter para salir..."
