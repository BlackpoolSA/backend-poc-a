
import logging
from fastapi import UploadFile
from typing import Annotated, List
from pathlib import Path
import json
import tempfile
import zipfile

from core.config import settings
from datetime import datetime
import re

# Configuración de logging
logger = logging.getLogger(__name__)

class Utils:
    
    @staticmethod
    def create_temp_file_name(file_path: Path, temp_dir: Path) -> str:
        """
        Crea un archivo temporal con la extensión original en minúscula.
        """
        # Crear archivo temporal con la extensión original en minúscula
        ext = file_path.suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, dir=temp_dir, suffix=ext) as temp_file:
            temp_file_path = temp_file.name
            
        return temp_file_path
    


    
    @staticmethod
    async def process_uploaded_files(files: List[UploadFile], temp_dir_name: str = ".chat_files") -> tuple[List[str], List[dict]]:
        """
        Procesa archivos subidos y los prepara para el agente.
        
        Args:
            files: Lista de archivos subidos
            temp_dir_name: Nombre del directorio temporal (por defecto ".chat_files")
        
        Returns:
            tuple: (nombres_archivos, metadatos_archivos)
        """
        files_processed = []
        files_metadata = []
        
        if not files:
            return files_processed, files_metadata
        
        # Verificar límite de archivos
        if len(files) > settings.MAX_TEMP_FILES:
            logger.warning(f"[UTL][FILES] Demasiados archivos: {len(files)} > {settings.MAX_TEMP_FILES}")
            files = files[:settings.MAX_TEMP_FILES]
        
        # Crear directorio temporal usando configuración
        temp_dir = Path(settings.TEMP_DIR) / temp_dir_name
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        for file in files:
            if not file.filename:
                continue
                
            try:
                # Verificar tamaño del archivo
                content = await file.read()
                if len(content) > settings.MAX_FILE_SIZE:
                    logger.warning(f"[CHAT][FILES] Archivo demasiado grande: {file.filename} ({len(content)} bytes > {settings.MAX_FILE_SIZE})")
                    continue
                
                if file.content_type not in settings.ALLOWED_TYPES:
                    logger.warning(f"[CHAT][FILES] DEBUG - Tipos permitidos: {settings.ALLOWED_TYPES}")
                    logger.warning(f"[CHAT][FILES] DEBUG - Tipo recibido: '{file.content_type}'")
                    logger.warning(f"[CHAT][FILES] Tipo de archivo no permitido: {file.filename} ({file.content_type})")
                    continue
                
                # Crear archivo temporal con nombre único usando create_temp_file_name
                temp_file_path = Utils.create_temp_file_name(Path(file.filename), temp_dir)
                
                # Guardar archivo temporalmente
                with open(temp_file_path, "wb") as f:
                    f.write(content)
                
                # Crear metadatos del archivo
                file_info = {
                    "filename"     : file.filename,
                    "size"         : len(content),
                    "content_type" : file.content_type or "application/octet-stream",
                    "temp_path"    : str(temp_file_path),
                    "content"      : content,
                    "upload_time"  : datetime.now().isoformat()
                }
                
                files_processed.append(file.filename)
                files_metadata.append(file_info)
                
                logger.info(f"[UTILS][FILES][UPLOADED] Archivo: [{file.filename}] ({len(content)} bytes, tipo: {file.content_type}) [SUCCESS]")
                
            except Exception as e:
                logger.error(f"[UTILS][FILES][UPLOADED] Error procesando archivo [{file.filename}]: {str(e)}")
                continue
        
        return files_processed, files_metadata


    @staticmethod
    def extract_zip_to_temp(zip_file_path: Path, temp_dir_name: str = ".agent_files") -> List[dict]:
        """
        Descomprime un archivo ZIP dentro del directorio temporal configurado
        (settings.TEMP_DIR) y la subcarpeta indicada (por defecto ".agent_files").

        Para cada archivo extraído con extensión soportada (.pdf, .xml, .json),
        crea una copia con nombre temporal siguiendo la estrategia de
        `create_temp_file_name` y devuelve una lista de metadatos compatibles con
        `process_uploaded_files` (al menos: filename, temp_path).

        Args:
            zip_file_path: Ruta al archivo .zip previamente almacenado en temp
            temp_dir_name: Subcarpeta dentro de settings.TEMP_DIR

        Returns:
            List[dict]: Metadatos de archivos extraídos y copiados a temp
        """
        extracted_metadata: List[dict] = []
        try:
            # Directorios base
            base_temp_dir = Path(settings.TEMP_DIR) / temp_dir_name
            base_temp_dir.mkdir(parents=True, exist_ok=True)

            # Carpeta única para extraer el zip (no se usa directamente para el pipeline)
            safe_stem = zip_file_path.stem
            extract_dir = base_temp_dir / f"{safe_stem}_unzipped"
            extract_dir.mkdir(parents=True, exist_ok=True)

            # Extraer
            with zipfile.ZipFile(zip_file_path, 'r') as zf:
                zf.extractall(extract_dir)

            # Extensiones soportadas en el flujo
            allowed_exts = {'.pdf', '.xml', '.json'}

            # Copiar archivos extraídos a rutas temporales con nombre único
            for p in extract_dir.rglob('*'):
                if not p.is_file():
                    continue
                ext = p.suffix.lower()
                if ext not in allowed_exts:
                    continue

                # Crear destino temporal con sufijo adecuado
                temp_target = Path(Utils.create_temp_file_name(p, base_temp_dir))
                try:
                    with open(p, 'rb') as src, open(temp_target, 'wb') as dst:
                        dst.write(src.read())
                    extracted_metadata.append({
                        "filename": p.name,
                        "temp_path": str(temp_target)
                    })
                except Exception as e:
                    logger.warning(f"[UTILS][ZIP] No se pudo copiar {p.name} a temp: {e}")

            logger.info(f"[UTILS][ZIP] Extraídos y preparados: {len(extracted_metadata)} archivo(s) desde [{zip_file_path.name}] [SUCCESS]")
        except Exception as e:
            logger.warning(f"[UTILS][ZIP] Error al descomprimir {zip_file_path}: {e}")

        return extracted_metadata

        
    def read_file_content(self, file_path: str) -> str:
        """
        Lee el contenido de un archivo y lo devuelve como string.
        La ruta debe ser relativa o absoluta, pero se recomienda usar rutas relativas al proyecto.

        Args:
            file_path (str): Ruta del archivo a leer.

        Returns:
            str: Contenido del archivo como string, o mensaje de error si no se puede leer.
        """
        try:
            # Convertir a Path para manejo multiplataforma
            path = Path(file_path)
            if not path.is_absolute():
                # Si la ruta es relativa, la resolvemos respecto al directorio base del proyecto
                base_dir = Path(__file__).parent.parent.parent.resolve()
                path = (base_dir / path).resolve()
            if not path.exists():
                logger.error(f"[UTILS][READ_FILE] Archivo no encontrado: {path}")
                return f"Error: Archivo no encontrado: {file_path}"
            # Leer el archivo como texto
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return content
        except Exception as e:
            logger.error(f"[UTILS][READ_FILE] Error al leer archivo {file_path}: {str(e)}")
            return f"Error al leer archivo: {str(e)}"

    @staticmethod
    def convert_to_serializable(obj):
        """Convierte objetos complejos a tipos serializables JSON."""
        if hasattr(obj, 'dict'):
            # Para objetos Pydantic
            return obj.dict()
        elif hasattr(obj, '__dict__'):
            # Para objetos con atributos
            result = {}
            for key, value in obj.__dict__.items():
                if not key.startswith('_'):  # Ignorar atributos privados
                    try:
                        json.dumps(value)  # Test si es serializable
                        result[key] = value
                    except (TypeError, ValueError):
                        result[key] = str(value)  # Convertir a string como fallback
            return result
        else:
            try:
                json.dumps(obj)  # Test si ya es serializable
                return obj
            except (TypeError, ValueError):
                return str(obj)  # Convertir a string como fallback

    @staticmethod
    def extract_json_from_text(text: str) -> str:
        """
        Extrae un objeto JSON válido desde un texto que puede venir con fences
        markdown (```json ... ```), y devuelve el JSON como string sin fences.
        Si no puede extraer un objeto válido, devuelve el texto recortado.
        """
        if not isinstance(text, str):
            return ""
        s = text.strip()
        if not s:
            return ""
        # 1) Bloque ```json ... ```
        fence = re.search(r"```json\s*([\s\S]*?)\s*```", s, flags=re.IGNORECASE)
        if fence:
            candidate = fence.group(1).strip()
            try:
                obj = json.loads(candidate)
                return json.dumps(obj, ensure_ascii=False)
            except Exception:
                pass
        # 2) Primer objeto {...}
        brace = re.search(r"\{[\s\S]*\}", s)
        if brace:
            candidate = brace.group(0)
            try:
                obj = json.loads(candidate)
                return json.dumps(obj, ensure_ascii=False)
            except Exception:
                pass
        # 3) Intento directo
        try:
            obj = json.loads(s)
            return json.dumps(obj, ensure_ascii=False)
        except Exception:
            return s
