import requests
import time
import zipfile
import json
import re
import shutil
from pathlib import Path
import sys

# Configuración
base_url = "http://159.112.150.232:8001"
root = Path(__file__).parent
in_file = root / "test_data" / "E54051224024325R001391884700.PDF"
out_file = root / "result.zip"
extract_dir = root / "result"

# Validaciones iniciales
if not in_file.exists():
    print(f"No existe: {in_file}")
    sys.exit(1)

if extract_dir.exists():
    shutil.rmtree(extract_dir)

# Consumo del endpoint
start = time.time()
with open(in_file, "rb") as f:
    resp = requests.post(f"{base_url}/ocr", files={"file": f})
resp.raise_for_status()

with open(out_file, "wb") as f:
    f.write(resp.content)

elapsed = round(time.time() - start, 2)
print(f"Listo: {out_file} (Tiempo_s={elapsed})")

# Extraer y validar ZIP
try:
    with zipfile.ZipFile(out_file, "r") as zf:
        zf.extractall(extract_dir)
except Exception as e:
    print(f"No se pudo extraer el ZIP de salida: {e}")
    sys.exit(1)

# Validar upload.md
md_path = extract_dir / "upload.md"
if not md_path.exists():
    print("Falta upload.md en el ZIP")
    sys.exit(1)

# Validar content_list.json
json_path = extract_dir / "content_list.json"
json_ok = False
if json_path.exists():
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            json.load(f)
        json_ok = True
    except Exception:
        json_ok = False

# Validar imágenes referenciadas en upload.md
md_content = md_path.read_text(encoding="utf-8")
img_matches = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md_content)
images_ok = True
for rel in img_matches:
    if rel.startswith("images/"):
        local_path = extract_dir / rel
        if not local_path.exists():
            images_ok = False
            break

print("- upload.md: OK")
print(
    f"- content_list.json: {'OK' if json_ok else ('INVL' if json_path.exists() else 'NO')}"
)
print(f"- Images: {'OK' if images_ok else 'FALTAN'}")

if not images_ok:
    sys.exit(2)

sys.exit(0)
