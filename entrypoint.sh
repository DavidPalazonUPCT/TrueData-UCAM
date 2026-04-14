#!/bin/bash

# Generar requirements.txt si no existe o está vacío
if [ ! -s /app/requirements.txt ]; then
    echo "Generando requirements.txt..."
    pip freeze > /app/requirements.txt
fi

# Ejecutar la inferencia
python /app/inference.py "$@"