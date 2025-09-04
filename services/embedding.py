"""
Agente de procesamiento simplificado para Oracle Cloud Infrastructure
"""
import logging
import tempfile
from pathlib import Path
import shutil

from core.config import settings
from schemas.oci_files import RAGFilesShema
from services.oci_bucket import OCIClient
from database import RAGFilesDB, RAGDocsDB
from services.ocr_mineru import process_file as ocr_process_file

logger = logging.getLogger(__name__)

class EmbeddingService:
    
    def __init__(self):
        self.temp_dir     = None
        self.oci_client   = None
        self.rag_files_db = None
        self.rag_docs_db  = None
        self.bucket_name  = None
        self._initialize_components()
    
    def _initialize_components(self):
        try:
            self.temp_dir = Path(settings.TEMP_DIR)
            self.temp_dir.mkdir(exist_ok=True)
            self.oci_client = OCIClient()
            self.rag_files_db = RAGFilesDB()
            self.rag_docs_db = RAGDocsDB()
            self.bucket_name = settings.OCI_DEFAULT_BUCKET
            logger.info("[OCI][RAG] Agente inicializado. [SUCCESS]")
        except Exception as e:
            logger.error(f"[OCI][RAG] Error al inicializar Agente: {str(e)}")
            raise
    
    def process_file(self, file_path: str) -> dict:
        """Procesa un archivo desde OCI Object Storage y devuelve un objeto tipo OCIObjectRAG."""
        try:
            object_name    = file_path.strip('/')
            
            # Si viene con el bucket incluido, normalizar a solo el object_name
            bucket_prefix = f"{self.bucket_name}/"
            if object_name.startswith(bucket_prefix):
                object_name = object_name[len(bucket_prefix):]

            file_path_obj  = Path(object_name)

            # Crear archivo temporal con la extensión original en minúscula
            ext = file_path_obj.suffix.lower()
            with tempfile.NamedTemporaryFile(delete=False, dir=self.temp_dir, suffix=ext) as temp_file:
                temp_file_path = temp_file.name                

            # Descargar archivo desde OCI
            self.oci_client.get_object(self.bucket_name, object_name, temp_file_path)

            # Obtener metadatos del archivo
            metadata  = self.oci_client.get_object_metadata(self.bucket_name, object_name)
            file_size = int(metadata.get('size', 0)) if metadata else 0
            file_trg  = f"{file_path_obj.stem}.md"

            # Procesar archivo con OCR
            ocr_result = ocr_process_file(Path(temp_file_path))

            data = []
            file_data = {
                'module_id'           : 1,
                'file_src_file_name'  : object_name,
                'file_src_size'       : file_size,
                'file_src_strategy'   : 'DocVLM',
                'file_trg_obj_name'   : file_trg,
                'file_trg_extraction' : ocr_result.get('file_trg_extraction'),
                'file_trg_tot_pages'  : ocr_result.get('file_trg_tot_pages', 1),
                'file_trg_tot_characters' : ocr_result.get('file_trg_tot_characters', 0),
                'file_trg_tot_time'   : ocr_result.get('file_trg_tot_time', '00:00:00'),
                'file_trg_language'   : ocr_result.get('file_trg_language', 'esa'),
                'file_trg_pii'        : 1,
                'file_description'    : 'Generado por App'
            }
            data.append(RAGFilesShema(**file_data))

            # Insertar archivo en la base de datos
            file_id = self.rag_files_db.insert_file(file_data)            
                        
            # Generar embeddings vectoriales
            self.rag_docs_db.call_embedding_procedure(file_id)

            # Eliminar archivo temporal
            Path(temp_file_path).unlink(missing_ok=True)
            # Eliminar el archivo temporal generado pero con extensión .md
            temp_md_path = Path(temp_file_path).with_suffix('.md')
            temp_md_path.unlink(missing_ok=True)
            # Eliminar la carpeta temporal de MinerU asociada al archivo procesado en una línea            
            shutil.rmtree(Path(".mineru_outputs") / f".mineru_{Path(temp_file_path).stem}", ignore_errors=True)
            
            # Construir respuesta compatible con backend.schemas.oci_bucket.OCIObjectRAG
            return {
                'file_id'              : file_id,
                'object_path'          : f"{self.bucket_name}/{object_name}",
                'object_name'          : file_path_obj.name,
                'object_type'          : 'file',
                'object_size'          : file_size,
                'last_modified'        : metadata.get('last_modified') if metadata else None,
                'has_embedding'        : True,
                'file_id'              : file_id,
                'file_src_file_name'   : object_name,
                'file_trg_extraction'  : ocr_result.get('file_trg_extraction'),
                'file_trg_tot_pages'   : ocr_result.get('file_trg_tot_pages'),
                'file_trg_tot_characters' : ocr_result.get('file_trg_tot_characters'),
                'file_trg_tot_time'       : ocr_result.get('file_trg_tot_time'),
            }
            
        except Exception as e:
            logger.error(f"[OCI][RAG] Error procesando el archivo: {str(e)}")
            raise

        finally:
            # Limpiar archivo temporal
            Path(temp_file_path).unlink(missing_ok=True)

    def process_text_content(self, text_content: str, file_name: str = "text_content.txt", 
                           file_trg_extraction: str = None, file_trg_tot_pages: int = 1,
                           file_trg_tot_characters: int = None, file_trg_tot_time: str = "00:00:00",
                           file_trg_language: str = "esa") -> dict:
        """
        Procesa contenido textual directamente y genera embeddings sin requerir un archivo desde un bucket.
        El contenido ya viene procesado por OCR, por lo que se omite ese paso.
        """
        try:
            # Obtener metadatos del contenido textual
            file_size = len(text_content.encode('utf-8'))
            file_trg = f"{Path(file_name).stem}.md"
            
            # Usar los valores proporcionados o calcularlos si no están disponibles
            if file_trg_extraction is None:
                file_trg_extraction = text_content
            
            if file_trg_tot_characters is None:
                file_trg_tot_characters = len(text_content)

            # Preparar datos del archivo
            file_data = {
                'module_id'           : 1,
                'file_src_file_name'  : file_name,
                'file_src_size'       : file_size,
                'file_src_strategy'   : 'TextContent',
                'file_trg_obj_name'   : file_trg,
                'file_trg_extraction' : file_trg_extraction,
                'file_trg_tot_pages'  : file_trg_tot_pages,
                'file_trg_tot_characters' : file_trg_tot_characters,
                'file_trg_tot_time'   : file_trg_tot_time,
                'file_trg_language'   : file_trg_language,
                'file_trg_pii'        : 1,
                'file_description'    : 'Generado por App - Contenido Textual Directo'
            }

            # Insertar archivo en la base de datos
            file_id = self.rag_files_db.insert_file(file_data)            
                        
            # Generar embeddings vectoriales
            self.rag_docs_db.call_embedding_procedure(file_id)
            
            # Construir respuesta compatible con backend.schemas.oci_bucket.OCIObjectRAG
            return {
                'file_id'              : file_id,
                'object_path'          : f"text_content/{file_name}",
                'object_name'          : file_name,
                'object_type'          : 'text',
                'object_size'          : file_size,
                'last_modified'        : None,  # No hay metadatos de OCI
                'has_embedding'        : True,
                'file_src_file_name'   : file_name,
                'file_trg_extraction'  : file_trg_extraction,
                'file_trg_tot_pages'   : file_trg_tot_pages,
                'file_trg_tot_characters' : file_trg_tot_characters,
                'file_trg_tot_time'       : file_trg_tot_time,
            }
            
        except Exception as e:
            logger.error(f"[OCI][RAG] Error procesando contenido textual: {str(e)}")
            raise

    def process_markdown_file(self, file_content: str, file_name: str, 
                            file_trg_extraction: str = None, file_trg_tot_pages: int = 1,
                            file_trg_tot_characters: int = None, file_trg_tot_time: str = "00:00:00",
                            file_trg_language: str = "esa") -> dict:
        """
        Procesa contenido de archivo markdown directamente y genera embeddings.
        El contenido ya viene procesado, por lo que se omite el paso de OCR.
        """
        try:
            logger.info(f"[OCI][RAG] Iniciando process_markdown_file")
            logger.info(f"[OCI][RAG] file_content length: {len(file_content)}")
            logger.info(f"[OCI][RAG] file_trg_extraction recibido: {len(file_trg_extraction) if file_trg_extraction else 0}")
            
            # Obtener metadatos del contenido del archivo
            file_size = len(file_content.encode('utf-8'))
            file_trg = f"{Path(file_name).stem}.md"
            
            # Usar los valores proporcionados o calcularlos si no están disponibles
            if file_trg_extraction is None or file_trg_extraction.strip() == "":
                file_trg_extraction = file_content
                logger.info(f"[OCI][RAG] file_trg_extraction era None o vacío, usando file_content")
            
            if file_trg_tot_characters is None:
                file_trg_tot_characters = len(file_content)

            logger.info(f"[OCI][RAG] file_trg_extraction final length: {len(file_trg_extraction)}")
            logger.info(f"[OCI][RAG] file_trg_extraction preview: {file_trg_extraction[:100]}...")

            # Preparar datos del archivo
            file_data = {
                'module_id'           : 1,
                'file_src_file_name'  : file_name,
                'file_src_size'       : file_size,
                'file_src_strategy'   : 'MarkdownFile',
                'file_trg_obj_name'   : file_trg,
                'file_trg_extraction' : file_trg_extraction,
                'file_trg_tot_pages'  : file_trg_tot_pages,
                'file_trg_tot_characters' : file_trg_tot_characters,
                'file_trg_tot_time'   : file_trg_tot_time,
                'file_trg_language'   : file_trg_language,
                'file_trg_pii'        : 1,
                'file_description'    : 'Generado por App - Archivo Markdown Directo'
            }

            logger.info(f"[OCI][RAG] file_data['file_trg_extraction'] length: {len(file_data['file_trg_extraction'])}")

            # Insertar archivo en la base de datos
            file_id = self.rag_files_db.insert_file(file_data)            
                        
            # Generar embeddings vectoriales
            self.rag_docs_db.call_embedding_procedure(file_id)
            
            # Construir respuesta compatible con backend.schemas.oci_bucket.OCIObjectRAG
            return {
                'file_id'              : file_id,
                'object_path'          : f"markdown_files/{file_name}",
                'object_name'          : file_name,
                'object_type'          : 'markdown',
                'object_size'          : file_size,
                'last_modified'        : None,  # No hay metadatos de OCI
                'has_embedding'        : True,
                'file_src_file_name'   : file_name,
                'file_trg_extraction'  : file_trg_extraction,
                'file_trg_tot_pages'   : file_trg_tot_pages,
                'file_trg_tot_characters' : file_trg_tot_characters,
                'file_trg_tot_time'       : file_trg_tot_time,
            }
            
        except Exception as e:
            logger.error(f"[OCI][RAG] Error procesando archivo markdown: {str(e)}")
            raise

    def get_embeddings_status(self) -> dict:
        """
        Obtiene el estado de embeddings para todos los archivos.
        Actúa como proxy hacia RAGFilesDB.
        """
        try:
            return self.rag_files_db.get_embeddings_status()
        except Exception as e:
            logger.error(f"[OCI][RAG] Error obteniendo estado de embeddings: {str(e)}")
            return {}

    def delete_embeddings(self, file_id: int):
        """
        Elimina los embeddings de un archivo específico.
        """
        try:
            self.rag_docs_db.delete_embeddings(file_id)
            logger.info(f"[OCI][RAG] Embeddings eliminados para el archivo con ID: {file_id}")
        except Exception as e:
            logger.error(f"[OCI][RAG] Error al eliminar embeddings para el archivo con ID {file_id}: {str(e)}")