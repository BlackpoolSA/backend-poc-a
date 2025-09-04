"""
Módulo para la interacción con OCI Object Storage.
"""
import os
import logging
from typing import Dict, Optional, Tuple
from pathlib import Path

import oci
from oci.object_storage import ObjectStorageClient
from oci.exceptions import ServiceError

from core.config import settings
from schemas.oci_bucket import OCIObjectRAG, OCIObjectTypeCounts, OCIObjectListResponse
from database.rag_files import RAGFilesDB

logger = logging.getLogger(__name__)

class OCIClient:
    """Cliente para interactuar con Oracle Cloud Infrastructure Object Storage."""
    
    def __init__(self):
        self.db_rag_files  = None
        self.profile       = None
        self.config        = None
        self.object_client = None
        self.namespace     = None
        self._initialize_client()
    
    def _initialize_client(self):
        try:
            self.db_rag_files = RAGFilesDB()
            self.profile = settings.OCI_PROFILE

            config_file = os.path.expanduser(settings.OCI_CONFIG_FILE)
            if not os.path.exists(config_file):
                raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_file}")
            
            self.config = oci.config.from_file(config_file, profile_name=self.profile)
            self.object_client = ObjectStorageClient(self.config)
            self.namespace = self.object_client.get_namespace().data
            logger.info(f"[OCI][BUK][CLI] Cliente inicilizado. [Profile={self.profile}] [Namespace={self.namespace}] [SUCCESS]")
        except Exception as e:
            logger.error(f"[OCI][BUK][CLI] Error al inicializar Object Storage: {str(e)}")
            raise
    
    def validate_bucket_path(self, bucket_path: str) -> Tuple[str, str]:
        """Valida y descompone la ruta de un bucket de OCI."""
        if not bucket_path or not bucket_path.strip():
            raise ValueError("La ruta del Bucket no puede estar vacía")
        
        parts       = bucket_path.strip('/').split('/', 1)
        bucket_name = parts[0]
        prefix      = parts[1] if len(parts) > 1 else ""
        
        if not bucket_name:
            raise ValueError("Nombre de Bucket inválido")

        # Para el listado, el prefijo no debe terminar en '/' si es para filtrar
        if prefix and not prefix.endswith('/'):
            prefix += '/'
        
        return bucket_name, prefix
            
    def list_structured_bucket_contents(self, bucket_name: str, prefix: str = "") -> OCIObjectListResponse:
        """
        Lista el contenido de un bucket/prefijo, diferenciando entre archivos y carpetas,
        y cuenta los tipos de archivo.
        """
        try:
            all_objects = oci.pagination.list_call_get_all_results(
                self.object_client.list_objects,
                self.namespace,
                bucket_name,
                prefix=prefix,
                delimiter='/',
                fields='size,timeModified'
            ).data

            data = []
            object_type_counts = {'pdf': 0, 'csv': 0, 'excel': 0, 'word': 0, 'json_file': 0, 'other': 0, 'embedding': 0}
            
            # Procesar carpetas (prefijos)
            for folder in all_objects.prefixes:
                folder_data = {
                    'object_name' : Path(folder).name,
                    'object_path' : f"{bucket_name}/{folder}",
                    'object_type' : 'folder'
                }
                data.append(OCIObjectRAG(**folder_data))
            
            # Recopilar rutas de archivos para consultar embeddings
            file_paths = []
            file_objects = []
            
            for obj in all_objects.objects:
                if (obj.size == 0 and obj.name.endswith('/')) or obj.name == prefix:
                    continue # Es una carpeta vacía o el propio directorio listado

                file_path = Path(obj.name)
                file_objects.append(obj)
                file_paths.append(obj.name)
                
                ext = file_path.suffix.lower()
                if ext == '.pdf':
                    object_type_counts['pdf'] += 1
                elif ext == '.csv':
                    object_type_counts['csv'] += 1
                elif ext in ['.xls', '.xlsx']:
                    object_type_counts['excel'] += 1
                elif ext in ['.doc', '.docx']:
                    object_type_counts['word'] += 1
                elif ext in ['.json']:
                    object_type_counts['json_file'] += 1
                else:
                    object_type_counts['other'] += 1

            # Obtener estado de embeddings para todos los archivos
            embeddings_status = self.db_rag_files.get_embeddings_status()

            # Procesar archivos con información de embeddings
            for obj in file_objects:
                file_path = Path(obj.name)
                embedding_info = embeddings_status.get(obj.name, {})
                
                # Log para debugging
                has_embedding = embedding_info.get('has_embedding', False)
                if has_embedding:
                    object_type_counts['embedding'] += 1
                    logger.info(f"[OCI][BUK][ATP] Embedding: [{Path(obj.name).name}][file_id={embedding_info.get('file_id')}]")
                    
                file_data = {
                    'object_name'          : file_path.name,
                    'object_path'          : f"{bucket_name}/{obj.name}",
                    'object_type'          : 'file',
                    'object_size'          : obj.size,
                    'last_modified'        : obj.time_modified.isoformat() if obj.time_modified else None,
                    'has_embedding'        : has_embedding,                    
                    'file_id'              : embedding_info.get('file_id'),
                    'file_src_file_name'   : embedding_info.get('file_src_file_name'),
                    'file_trg_extraction'  : embedding_info.get('file_trg_extraction'),
                    'file_trg_tot_pages'   : embedding_info.get('file_trg_tot_pages'),
                    'file_trg_tot_characters' : embedding_info.get('file_trg_tot_characters'),
                    'file_trg_tot_time'       : embedding_info.get('file_trg_tot_time'),
                    'file_date'               : embedding_info.get('file_date')
                }
                data.append(OCIObjectRAG(**file_data))

            response_data = {
                'bucket_path'        : f"{bucket_name}/{prefix}",
                'total_objects'      : len(data),
                'object_type_counts' : OCIObjectTypeCounts(**object_type_counts),
                'object_rag'         : sorted(data, key=lambda x: (0 if x.object_type == 'folder' else 1, x.object_name))
            }
            return OCIObjectListResponse(**response_data)

        except ServiceError as e:
            logger.error(f"[OCI][BUK] Error de servicio al listar contenido estructurado: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"[OCI][BUK] Error inesperado al listar contenido estructurado: {str(e)}")
            raise

    def get_object(self, bucket_name: str, object_name: str, local_path: str) -> bool:
        """
        Retrieves an object from the OCI Bucket.

        Args:
            object_name (str): Name of the object to retrieve.

        Returns:
            Response object or a dictionary with error details.
        """
        try:
            response = self.object_client.get_object(self.namespace, bucket_name, object_name)
            
            if response.status == 200:
                logger.info(f"[OCI][BUK] Archivo descargado [{Path(object_name).name}] [SUCCESS]")
                
                # Escribir contenido al disco de forma segura
                with open(local_path, 'wb') as f:
                    # Preferir el stream si existe, si no, usar response.data.content
                    raw = getattr(response.data, 'raw', None)
                    if raw and hasattr(raw, 'stream'):
                        for chunk in raw.stream(1024 * 1024, decode_content=False):
                            if not chunk:
                                continue
                            f.write(chunk)
                    else:
                        content = getattr(response.data, 'content', None)
                        if content:
                            f.write(content)
                        else:
                            # Último recurso: leer el body completo
                            f.write(response.data.read())
            else:
                logger.error(f"[Error] Retrieving Object:\n{response}")
                return None
        except Exception as e:
            logger.error(f"[Error] Retrieving Object:\n{e}")
            return None
    # =====================================
    def download_object(self, bucket_name: str, object_name: str, local_path: str) -> bool:
        try:
            response = self.object_client.get_object(self.namespace, bucket_name, object_name)
            status = getattr(response, 'status', None) or getattr(response, 'status_code', None)

            if status and int(status) != 200:
                logger.error(f"[OCI][BUK] Error HTTP al descargar [{object_name}]: status={status}")
                return False

            # Escribir contenido al disco de forma segura
            with open(local_path, 'wb') as f:
                # Preferir el stream si existe, si no, usar response.data.content
                raw = getattr(response.data, 'raw', None)
                if raw and hasattr(raw, 'stream'):
                    for chunk in raw.stream(1024 * 1024, decode_content=False):
                        if not chunk:
                            continue
                        f.write(chunk)
                else:
                    content = getattr(response.data, 'content', None)
                    if content:
                        f.write(content)
                    else:
                        # Último recurso: leer el body completo
                        f.write(response.data.read())

            # Validar que el archivo no esté vacío
            try:
                if os.path.getsize(local_path) == 0:
                    logger.error(f"[OCI][BUK] Descarga vacía para [{object_name}]")
                    return False
            except Exception:
                pass

            logger.info(f"[OCI][BUK] Objeto descargado: [{object_name}] [SUCCESS]")
            return True
        except ServiceError as e:
            logger.error(f"[OCI][BUK] Error de servicio al descargar [{object_name}]: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"[OCI][BUK] Error inesperado al descargar [{object_name}]: {str(e)}")
            return False


    
    def get_object_metadata(self, bucket_name: str, object_name: str) -> Optional[Dict]:
        try:
            head_object_response = self.object_client.head_object(
                self.namespace, bucket_name, object_name
            )
            return {
                'size': head_object_response.headers.get('content-length'),
                'etag': head_object_response.headers.get('etag'),
                'last_modified': head_object_response.headers.get('last-modified'),
                'content_type': head_object_response.headers.get('content-type')
            }
        except ServiceError as e:
            logger.error(f"[OCI] Error al obtener metadatos de {object_name}: {str(e)}")
            return None





