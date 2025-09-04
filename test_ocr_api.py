#!/usr/bin/env python3
# test.py — Ejemplo mínimo de uso del endpoint /ocr

import os
import sys
import time
import requests
from pathlib import Path

base_url = "http://159.112.135.70:8001"
script_dir = Path(__file__).parent
in_file = Path(
    r"C:\Users\ldavi\Downloads\E54051224024325R001391884700 1\E54051224024325R001391884700.PDF"
)
out_file = script_dir / "result.zip"

# Verificar que existe el archivo de entrada
if not in_file.exists():
    print(f"Error: No existe: {in_file}", file=sys.stderr)
    sys.exit(1)

# Iniciar cronómetro
start_time = time.time()

try:
    # Preparar los datos del formulario
    with open(in_file, "rb") as f:
        files = {"file": f}
        data = {"per_worker_mb": "512", "workers_cap": "2"}

        # Hacer la petición POST
        response = requests.post(f"{base_url}/ocr", files=files, data=data)
        response.raise_for_status()  # Lanza excepción si hay error HTTP

        # Guardar la respuesta en el archivo de salida
        with open(out_file, "wb") as output:
            output.write(response.content)

    # Calcular tiempo transcurrido
    elapsed_time = round(time.time() - start_time, 2)
    print(f"Listo: {out_file} (Tiempo_s={elapsed_time})")

except requests.exceptions.RequestException as e:
    print(f"Error en la petición: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
