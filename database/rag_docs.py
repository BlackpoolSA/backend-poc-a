"""
Módulo para la gestión de la tabla RAG_DOCS y operaciones de vectores.
"""
import logging
from database.connection import Connection
from langchain_community.embeddings.oci_generative_ai import OCIGenAIEmbeddings
from langchain_community.vectorstores import OracleVS
from core.config import settings

logger = logging.getLogger(__name__)

class RAGDocsDB:
    """
    Clase de servicio para interactuar con las operaciones de la base de datos
    relacionadas con documentos y vectores.
    """

    def __init__(self):
        self.db_connector = Connection()


    def call_embedding_procedure(self, file_id: int):
        """
        Ejecuta el procedimiento almacenado para crear embeddings para un archivo.
        """
        try:
            procedure_name = "SP_RAG_EMBEDDING"
            params         = (file_id,)
            self.db_connector.execute_procedure(procedure_name, params)
            logger.info(f"[OCI][RAG_DOCS] Procedimiento: [{procedure_name}][file_id={file_id}] [SUCCESS]")

        except Exception as e:
            logger.error(f"[OCI][RAG_DOCS] Error al generar Embeddings con ID: {file_id}: {str(e)}")
            return False


    def get_vector_store(self) -> OracleVS:
        """
        Crea y devuelve una instancia de Oracle Vector Store.
        """
        embeddings = OCIGenAIEmbeddings(
            model_id         = settings.CON_GEN_AI_EMB_MODEL_ID,
            service_endpoint = settings.CON_GEN_AI_SERVICE_ENDPOINT,
            compartment_id   = settings.CON_COMPARTMENT_ID,
            auth_type        = "API_KEY",
            auth_profile     = settings.OCI_PROFILE,
        )
        
        # OracleVS maneja su propia conexión, por lo que le pasamos un cliente nuevo.
        return OracleVS(
            client             = self.db_connector.get_connection(),
            embedding_function = embeddings,
            table_name         = 'rag_docs'
        )