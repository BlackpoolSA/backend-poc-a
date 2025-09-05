from __future__ import annotations
import os
import re
import sys
import json
import time
import base64
import zipfile
import tempfile
import requests
from pathlib import Path
from typing import Optional, Dict, List
import shutil
from PIL import Image
import fitz  # PyMuPDF
import pytesseract
import io
from langchain_community.chat_models import ChatOCIGenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers.string import StrOutputParser
from dotenv import load_dotenv
import logging

try:
    from core.config import settings
except ImportError as e:
    print(f"Error importing settings: {e}")
    raise

load_dotenv()
logger = logging.getLogger(__name__)

# =====================================
# Configuración básica
# =====================================
TEMP_DIR = Path(os.getenv("OCR_TEMP_DIR", "temp")).resolve()
OUTPUT_ROOT = TEMP_DIR / ".mineru_outputs"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# Extensiones soportadas por MinerU
SUPPORTED_EXTS: Dict[str, str] = {
    # Documentos
    ".pdf": "pdf",
    # Imágenes raster
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    # Office
    ".docx": "office",
    ".doc": "office",
    ".pptx": "office",
    ".ppt": "office",
    # Texto
    ".txt": "text",
}

# =====================================
# Prompt VLM provisto por el usuario
# =====================================
VLM_OCR_PROMPT = """
You are an expert in Optical Character Recognition (OCR) and Markdown formatting. Your task is to transcribe the content of images into clean, accurate Markdown format.

## General Rules
- **Priority**: Transcribe all readable text. If something is unreadable, replace it with `[Illegible]`.
- **Language**: Keep the original language of each text segment.
- **No explanations**: Do not explain decisions or add comments outside of the transcription.
- **Order**: Maintain the visual reading order (top-to-bottom, left-to-right).
- **Remove noise**: Ignore repeated headers/footers or watermarks unless they contain relevant information.

## Markdown Formatting
- **Headings**: Use `#`, `##`, `###` according to visual hierarchy.
- **Paragraphs**: Use normal Markdown paragraphs without excessive blank lines.
- **Lists**: Use `-` for bullets and `1.` for numbered lists. Maintain indentation for sublevels.
- **Emphasis**: Use `**bold**` or `_italic_` only if visually clear in the original document.
- **Blockquotes**: Use `>` for visually distinct quotes or notes.
- **Code blocks**: Use triple backticks for monospace/code fragments.
- **Links**: Keep URLs as-is or format them as `[text](url)` if both appear.

## Tables
- Always convert detected tables into **GitHub-style Markdown tables** with pipes `|`.
- First row must be the header, followed by a separator line with `---`.
- Align columns visually: numeric columns right-aligned (`---:`), text left-aligned (`:---`), centered if evident (`:---:`).
- Multi-line cells: separate lines with `<br>` inside the cell.
- Rowspan/colspan: repeat the value and mark with `(merge)`.
- Mark unreadable cells as `[Illegible]`.
- For very wide tables, split into smaller logical parts, naming them ("Table 1A", "Table 1B").
Example:
| Field       | Description        | Value   |
|:------------|:-------------------|--------:|
| Patient     | Full name          | Juan P. |
| Diagnosis   | ICD-10 (merge)     | A09     |

## Special Structures
- **Forms**: Represent as `Field: Value` lists or tables if grid-based.
- **Multi-level lists**: Use 3 spaces per indentation level.
- **Equations**: Use LaTeX format `$...$` inline or `$$ ... $$` for blocks.
- **Stamps/Signatures**: Mark as `**[Stamp]**`, `**[Signature]**` or both; transcribe any nearby readable text.
- **Checkboxes**: Use `☑` (checked) or `☐` (unchecked) followed by the label.
- **Diagrams/Charts/Images**: Add `**Figure:** <brief description>` plus any readable text within as a list or table.

Example figure:
**Figure:** Flow diagram for CIE process (Validation → Coding → Review).
- Nodes: Reception, Validation, Coding, Review, Approval.
- Arrows: Sequential; loop between Coding ↔ Review.

## Multi-column Pages
- If the page has multiple columns, transcribe column 1 fully, then column 2, etc., separated by a horizontal rule `---`.

## Metadata & Marginal Notes
- Describe any non-textual content briefly ("**Figure:** schematic of …").
- Marginal notes: include at the end of the related section, starting with `> Marginal note:`.

## Uncertainty Handling
- Use `[Illegible]` for uncertain text, or `[[text?]]` for possible alternatives.
- Never fill in with outside knowledge.

## QR-CODE
- If the page contains a QR-CODE, use `[QR-CODE]`.

## Blank/Unreadable Pages
- If the page is completely blank or unreadable, output only: **[Unreadable or Blank Document]**

## Output
- Return only the final Markdown content of the page.
- Do not include this instruction text or any explanation.
"""

# =====================================
# Utilidades
# =====================================


def _fmt_hms(total_seconds: int) -> str:
    """Formatea segundos en HH:MM:SS"""
    total_seconds = int(total_seconds)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


# =====================================
# VLM wrapper
# =====================================


class VLMAnalyzer:
    def call_vlm(self, image_path: Path) -> Optional[str]:
        from core.config import settings

        try:
            # Initialize the LLM model
            llm = ChatOCIGenAI(
                model_id=settings.CON_GEN_AI_CHAT_MODEL_ID,
                service_endpoint=settings.CON_GEN_AI_SERVICE_ENDPOINT,
                compartment_id=settings.CON_COMPARTMENT_ID,
                provider=settings.CON_GEN_AI_CHAT_MODEL_PROVIDER,
                is_stream=False,
                auth_type="API_KEY",
                auth_profile=settings.OCI_PROFILE,
                model_kwargs={"temperature": 1},
            )

            # Prompt template
            prompt_template = ChatPromptTemplate.from_messages(
                [
                    ("system", VLM_OCR_PROMPT),
                    (
                        "user",
                        [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:image/jpeg;base64,{input_imagen}"
                                },
                                "detail": "high",
                            }
                        ],
                    ),
                ]
            )

            # Chain
            chain = prompt_template | llm | StrOutputParser()

            # Encode the single image to base64
            with open(image_path, "rb") as img_file:
                encoded_image = base64.b64encode(img_file.read()).decode("utf-8")

            if not encoded_image:
                logger.warning(
                    f"[OCR][MINERU][DOCVLM] Could not encode image {image_path}"
                )
                return None

            # Invoke the chain for the single image
            result = chain.invoke({"input_imagen": encoded_image})

            content = str(result)
            if content.startswith("```markdown"):
                content = content[len("```markdown") :].strip()
            if content.endswith("```"):
                content = content[: -len("```")].strip()

            logger.warning(f"[OCR][MINERU][DOCVLM] Imagen procesada [SUCCESS]")
            return content
        except Exception as e:
            logger.warning(f"[OCR][MINERU][DOCVLM] VLM OCR falló: {e}")
            return None


# =====================================
# Core: OCR API Service
# =====================================


def _call_ocr_api(input_path: Path) -> tuple[str, dict]:
    """Llama al servicio OCR externo y devuelve el contenido del archivo markdown y el resultado de auditoría."""
    from core.config import settings

    logger.info(f"[OCR][API] Iniciando llamada al servicio OCR externo... [START]")

    try:
        # Preparar los datos para la API - formato simplificado
        with open(input_path, "rb") as f:
            files = {"file": f}
            
            # Realizar la llamada a la API
            response = requests.post(
                settings.OCR_SERVICE_URL,
                files=files,
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"OCR API failed with status {response.status_code}: {response.text}"
            )

        # Crear un archivo temporal para el ZIP
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_zip:
            temp_zip.write(response.content)
            temp_zip_path = temp_zip.name

        # Extraer el contenido del ZIP
        markdown_content = ""
        with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
            # Buscar el archivo upload.md dentro del ZIP
            for file_info in zip_ref.filelist:
                if file_info.filename == "upload.md":
                    with zip_ref.open("upload.md") as md_file:
                        markdown_content = md_file.read().decode("utf-8")
                    break

            if not markdown_content:
                # Si no encuentra upload.md, buscar cualquier archivo .md
                for file_info in zip_ref.filelist:
                    if file_info.filename.endswith(".md"):
                        with zip_ref.open(file_info.filename) as md_file:
                            markdown_content = md_file.read().decode("utf-8")
                        break

        # Limpiar archivo temporal
        os.unlink(temp_zip_path)

        if not markdown_content:
            raise RuntimeError(
                "No se encontró archivo markdown en la respuesta del servicio OCR"
            )

        logger.info(f"[OCR][API] Servicio OCR externo completado exitosamente [END]")

        # Ya no llamamos a la API de auditoría externa
        # La auditoría se ejecuta directamente desde /glosa usando MedicalAuditService

        return markdown_content, {}

    except requests.exceptions.Timeout:
        logger.error("[OCR][API] Timeout en la llamada al servicio OCR externo")
        raise RuntimeError("Timeout en la llamada al servicio OCR externo")
    except requests.exceptions.RequestException as e:
        logger.error(f"[OCR][API] Error en la llamada al servicio OCR externo: {e}")
        raise RuntimeError(f"Error en la llamada al servicio OCR externo: {e}")
    except Exception as e:
        logger.error(f"[OCR][API] Error inesperado: {e}")
        raise RuntimeError(f"Error inesperado en el servicio OCR: {e}")


def _replace_images_with_vlm(md_text: str, vlm: VLMAnalyzer) -> str:
    """Procesa el texto markdown y sustituye las imágenes por el análisis del VLM."""

    def _replacer(m: re.Match) -> str:
        rel = m.group(1)
        # Buscar la imagen en el directorio temporal
        img_path = TEMP_DIR / rel

        if not img_path.exists():
            return f"> [Imagen no encontrada: {rel}]"
        try:
            analysis = vlm.call_vlm(img_path)
        except Exception as e:
            logger.warning(f"No se pudo abrir/analizar imagen {img_path}: {e}")
            analysis = None
        if not analysis:
            return f"![img]({rel})"  # fallback: mantener imagen
        return f"> **[DocVLM]:**\n\n{analysis}\n"

    IMG_MD = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
    new_text = IMG_MD.sub(_replacer, md_text)

    return new_text


def _discover_supported_files(temp_dir: Path) -> List[Path]:
    files: List[Path] = []
    if not temp_dir.exists():
        return files
    for p in temp_dir.iterdir():
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            files.append(p)
    return sorted(files)


# =====================================
# API del servicio (para ser invocado por otro módulo)
# =====================================


def process_file(input_path: Path) -> Dict:
    """Procesa un archivo con el servicio OCR externo + auditoría + post-proceso VLM y devuelve el dict requerido."""
    t0 = time.time()

    # Autorrotación previa para PDFs con OSD
    src_path = input_path
    if input_path.suffix.lower() == ".pdf":
        try:
            src_path = _autorotate_pdf_osd(input_path)
        except Exception as e:
            logger.warning(f"No se pudo autorrotar {input_path.name}: {e}")

    # Llamar al servicio OCR externo (sin auditoría)
    md_text, _ = _call_ocr_api(src_path)

    # Aplicar post-procesamiento VLM si es necesario
    vlm = VLMAnalyzer()
    md_text = _replace_images_with_vlm(md_text, vlm)

    elapsed = time.time() - t0

    # Obtener el número de páginas (aproximado por líneas que contengan #)
    num_pages = len(
        [line for line in md_text.split("\n") if line.strip().startswith("#")]
    )
    if num_pages == 0:
        num_pages = 1

    result = {
        "file_src_strategy": "RAG",
        "file_trg_extraction": md_text,
        "markdown_content": md_text,  # Agregar para que esté disponible en /glosa y /process
        "file_trg_tot_pages": num_pages,
        "file_trg_tot_characters": len(md_text),
        "file_trg_tot_time": _fmt_hms(elapsed),
    }

    # La auditoría se ejecuta directamente desde /glosa usando MedicalAuditService
    # No se incluye aquí el resultado de auditoría

    # Crear ruta de salida con misma carpeta y nombre, pero .md
    md_path = input_path.with_suffix(".md")

    # Guardar
    md_path.write_text(md_text, encoding="utf-8")

    return result


# =====================================
# OSD autorotation helpers
# =====================================


def _page_image(page: "fitz.Page", dpi: int = 150) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def _autorotate_pdf_osd(input_pdf: Path, dpi_preview: int = 150) -> Path:
    doc = fitz.open(str(input_pdf))
    rotated = False
    for page in doc:
        try:
            img = _page_image(page, dpi=dpi_preview)
            osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
            angle = int(osd.get("rotate", 0)) % 360
        except Exception:
            angle = 0
        if angle in (90, 180, 270):
            page.set_rotation((page.rotation + angle) % 360)
            rotated = True
    if rotated:
        out_pdf = input_pdf.with_name(input_pdf.stem + "_rot.pdf")
        doc.save(str(out_pdf), garbage=4, deflate=True)
        doc.close()
        return out_pdf
    doc.close()
    return input_pdf


def process_all_in_temp(temp_dir: Path = TEMP_DIR) -> List[Dict]:
    results: List[Dict] = []
    for f in _discover_supported_files(temp_dir):
        try:
            logger.info(f"Procesando {f.name}")
            results.append(process_file(f))
        except Exception as e:
            logger.warning(f"Error procesando {f}: {e}")
    return results


# =====================================
# CLI simple para pruebas / integración
# =====================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="OCR RAG Services (External API + VLM post-proceso)"
    )
    parser.add_argument(
        "--temp-dir",
        default=str(TEMP_DIR),
        help="Directorio de entrada (default: temp)",
    )
    args = parser.parse_args()

    temp_dir = Path(args.temp_dir).resolve()
    out = []
    for f in _discover_supported_files(temp_dir):
        try:
            out.append(process_file(f))
        except Exception as e:
            out.append({"file_src_strategy": "RAG", "error": str(e), "source": str(f)})
    print(json.dumps(out, ensure_ascii=False))
