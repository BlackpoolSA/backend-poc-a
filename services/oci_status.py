"""
Módulo para verificar el estado de los servicios de Oracle Cloud Infrastructure (OCI).
"""
import logging
import asyncio
from typing import Dict

from services.oci_bucket import OCIClient
from database import Connection
from core.config import settings

logger = logging.getLogger(__name__)

class OCIStatusChecker:
    """Clase para verificar el estado de los componentes de OCI."""
    
    def __init__(self):
        self.oci_client = OCIClient()
        self.db_connection = Connection()

    def get_oci_connection_status(self) -> Dict:
        """Obtener estado de la conexión OCI."""
        try:
            namespace = self.oci_client.namespace
            buckets = []
            try:
                list_buckets_response = self.oci_client.object_client.list_buckets(
                    namespace_name=namespace,
                    compartment_id=settings.CON_COMPARTMENT_ID,
                    limit=10
                )

                buckets = [bucket.name for bucket in list_buckets_response.data]
            except Exception as e:
                logger.warning(f"No se pudieron listar buckets: {str(e)}")
            
            return {
                'connected': True,
                'profile': settings.OCI_PROFILE,
                'namespace': namespace,
                'buckets_accessible': buckets,
                'error_message': None
            }
        except Exception as e:
            return {
                'connected': False,
                'profile': settings.OCI_PROFILE,
                'namespace': None,
                'buckets_accessible': [],
                'error_message': str(e)
            }
    
    async def get_database_status_async(self) -> Dict:
        """Versión asíncrona de get_database_status para poder usar timeouts."""
        loop = asyncio.get_running_loop()
        try:
            # Ejecutar la operación de base de datos síncrona en un hilo separado
            return await loop.run_in_executor(None, self._get_database_status_sync)
        except Exception as e:
            logger.error(f"Error en la ejecución asíncrona del estado de la BD: {str(e)}")
            return self._get_error_db_status(str(e))

    def _get_database_status_sync(self) -> Dict:
        """Lógica de obtención de estado de la base de datos (síncrona)."""
        try:
            connection = self.db_connection.get_connection()
            cursor = connection.cursor()
            
            cursor.execute("SELECT SYS_CONTEXT('USERENV', 'DB_NAME') FROM DUAL")
            db_name = cursor.fetchone()[0]
            
            cursor.execute("SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') FROM DUAL")
            schema_name = cursor.fetchone()[0]
            
            cursor.execute("SELECT table_name FROM user_tables WHERE table_name NOT LIKE 'VECTOR$%%' ORDER BY table_name")
            tables = [row[0] for row in cursor.fetchall()]
            
            cursor.execute("SELECT view_name FROM user_views ORDER BY view_name")
            views = [row[0] for row in cursor.fetchall()]

            cursor.execute("SELECT object_name FROM user_objects WHERE object_type = 'PROCEDURE' ORDER BY object_name")
            procedures = [row[0] for row in cursor.fetchall()]

            return {
                'connected': True,
                'database_name': db_name,
                'schema_name': schema_name,
                'tables': tables,
                'views': views,
                'procedures': procedures,
                'error_message': None
            }
        except Exception as e:
            # Re-lanzamos la excepción para que el wrapper asíncrono la capture
            raise e

    def get_database_status(self) -> Dict:
        """Punto de entrada síncrono para mantener compatibilidad si es necesario."""
        return self._get_database_status_sync()

    def _get_error_db_status(self, error_message: str) -> Dict:
        """Devuelve un diccionario de estado de error para la BD."""
        logger.error(f"Error al obtener estado de la base de datos: {error_message}")
        return {
            'connected': False, 
            'error_message': error_message,
            'database_name': None,
            'schema_name': None,
            'tables': [],
            'views': [],
            'procedures': []
        }

