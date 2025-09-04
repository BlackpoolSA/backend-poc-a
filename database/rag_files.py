"""
Módulo para la gestión de la tabla RAG_FILES en la base de datos.
"""
import logging
from typing import Dict, Optional, Any

from database.connection import Connection

logger = logging.getLogger(__name__)

class RAGFilesDB:
    """Clase para gestionar operaciones CRUD en la tabla RAG_FILES."""

    def __init__(self):
        self.db_connector = Connection()

    def get_embeddings_status(self) -> Dict[str, Any]:
        """
        Obtener el estado de embeddings para todos los archivos con file_state = 1.
        """
        try:
            query = """
                SELECT
                    file_id, module_id, file_src_file_name, file_src_size,
                    file_src_strategy, file_trg_obj_name, file_trg_extraction,
                    file_trg_tot_pages, file_trg_tot_characters, file_trg_tot_time,
                    file_trg_language, file_trg_pii, file_description,
                    file_version, file_state, file_date
                FROM
                    rag_files
                WHERE
                    file_state = 1
            """

            results = self.db_connector.execute_select(query)
            logger.info(f"[OCI][RAG_FILES] Embedding(s): {len(results)} en Total [SUCCESS]")

            response: Dict[str, Any] = {}
            for row in results:
                file_src_file_name = row[2]
                response[file_src_file_name] = {
                    'has_embedding'        : True,
                    'file_id'              : row[0],
                    'module_id'            : row[1],
                    'file_src_file_name'   : row[2],
                    'file_src_size'        : row[3],
                    'file_src_strategy'    : row[4],
                    'file_trg_obj_name'    : row[5],
                    'file_trg_extraction'  : row[6],
                    'file_trg_tot_pages'   : row[7],
                    'file_trg_tot_characters': row[8],
                    'file_trg_tot_time'    : row[9],
                    'file_trg_language'    : row[10],
                    'file_trg_pii'         : row[11],
                    'file_description'     : row[12],
                    'file_version'         : row[13],
                    'file_state'           : row[14],
                    'file_date'            : row[15].isoformat() if hasattr(row[15], 'isoformat') else str(row[15]) if row[15] else None,
                }

            return response

        except Exception as e:
            logger.error(f"[OCI][RAG_FILES] Error al consultar estado de embeddings: {str(e)}")
            return {}


    def insert_file(self, file_data: Dict[str, Any]) -> Optional[int]:
        """
        Inserta un registro inicial para un archivo con metadatos básicos.
        """
        try:
            logger.info(f"[OCI][RAG_FILES] Insertando archivo: {file_data['file_src_file_name']}")
            logger.info(f"[OCI][RAG_FILES] file_trg_extraction length: {len(file_data['file_trg_extraction']) if file_data['file_trg_extraction'] else 0}")
            logger.info(f"[OCI][RAG_FILES] file_trg_extraction preview: {file_data['file_trg_extraction'][:100] if file_data['file_trg_extraction'] else 'None'}...")
            
            query = """
                INSERT INTO rag_files(
                    module_id,
                    file_src_file_name,
                    file_src_size,
                    file_src_strategy,
                    file_trg_obj_name,
                    file_trg_extraction,
                    file_trg_tot_pages,
                    file_trg_tot_characters,
                    file_trg_tot_time,
                    file_trg_language,
                    file_trg_pii,
                    file_description
                )
                VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12)
                RETURNING file_id INTO :13
            """
            params = (
                file_data['module_id'],
                file_data['file_src_file_name'],
                file_data['file_src_size'],
                file_data['file_src_strategy'],
                file_data['file_trg_obj_name'],
                file_data['file_trg_extraction'],
                file_data['file_trg_tot_pages'],
                file_data['file_trg_tot_characters'],
                file_data['file_trg_tot_time'],
                file_data['file_trg_language'],
                file_data['file_trg_pii'],
                file_data['file_description']
            )
            
            logger.info(f"[OCI][RAG_FILES] Parámetro 6 (file_trg_extraction) length: {len(params[5]) if params[5] else 0}")
            
            file_id = self.db_connector.execute_query(query, params)
            logger.info(f"[OCI][RAG_FILES] Registro insertado [file_id={file_id}] [SUCCESS]")

            return file_id

        except Exception as e:
            logger.error(f"[OCI][RAG_FILES] Error al insertar archivo: {str(e)}")
            return None

    def delete_file_with_docs(self, file_id: int) -> bool:
        """
        Elimina un archivo y sus documentos asociados.
        Primero elimina de rag_docs, luego de rag_files.
        """
        try:
            # Primero eliminar de rag_docs
            query_docs = "DELETE FROM rag_docs WHERE file_id = :1"
            params = (file_id,)
            self.db_connector.execute_query(query_docs, params)
            logger.info(f"[OCI][RAG_FILES] Registro eliminado con file_id: {file_id} [SUCCESS]")
            
            # Luego eliminar de rag_files
            query_files = "DELETE FROM rag_files WHERE file_id = :1"
            self.db_connector.execute_query(query_files, params)
            logger.info(f"[OCI][RAG_DOCS] Registro eliminado con file_id: {file_id} [SUCCESS]")
            
            return True

        except Exception as e:
            logger.error(f"[OCI][RAG_FILES][RAG_DOCS] Error al eliminar con ID: {file_id}: {str(e)}")
            return False

