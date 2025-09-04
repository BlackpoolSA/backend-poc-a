import os
import logging
import oracledb

from core.config import settings

logger = logging.getLogger(__name__)

class Connection:
    """
    Manages Oracle database connections.
    """
    def __init__(self):
        self.user = settings.CON_ADB_DEV_USER_NAME
        self.password = settings.CON_ADB_DEV_PASSWORD
        self.dsn = settings.CON_ADB_DEV_SERVICE_NAME
        self.config_dir = settings.CON_ADB_WALLET_LOCATION
        self.wallet_location = settings.CON_ADB_WALLET_LOCATION
        self.wallet_password = settings.CON_ADB_WALLET_PASSWORD

    def get_connection(self):
        """
        Establishes and returns a new Oracle database connection.
        """
        try:
            if not self.user or not self.password or not self.dsn:
                raise RuntimeError("Variables de entorno de ADB incompletas (usuario/clave/dsn)")
            return oracledb.connect(
                user=self.user,
                password=self.password,
                dsn=self.dsn,
                config_dir=self.config_dir,
                wallet_location=self.wallet_location,
                wallet_password=self.wallet_password
            )
        except oracledb.DatabaseError as e:
            error, = e.args
            raise RuntimeError(f"Error connecting to the database: {error.message}")
        except Exception as e:
            raise
    
    def execute_query(self, query: str, params: tuple, fetch: str = None):
        """
        Ejecuta una consulta en la base de datos de forma segura.
        
        Args:
            query (str): La consulta SQL a ejecutar.
            params (tuple): Los parámetros para la consulta.
            fetch (str): El tipo de resultado a obtener ('one', 'all', None).
            
        Returns:
            El resultado de la consulta o el ID del último registro insertado.
        """
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if "RETURNING" in query:
                id_var = cursor.var(oracledb.NUMBER)
                params = params + (id_var,)
                cursor.execute(query, params)
                result = id_var.getvalue()[0]
            else:
                cursor.execute(query, params)
                if fetch == 'one':
                    result = cursor.fetchone()
                elif fetch == 'all':
                    result = cursor.fetchall()
                else:
                    result = None
            
            conn.commit()
            return result
        except oracledb.DatabaseError as e:
            logger.error(f"[OCI][ADB] Error de base de datos: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    def execute_select(self, query: str, params: dict = None, fetch_one: bool = False):
        """
        Ejecuta una consulta SELECT de forma segura y retorna los resultados.
        
        Args:
            query (str): La consulta SELECT SQL a ejecutar.
            params (dict): Los parámetros para la consulta (opcional).
            fetch_one (bool): Si True, retorna solo un registro; si False, retorna todos.
            
        Returns:
            list|tuple|None: Los resultados de la consulta.
        """
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Ejecutar consulta con o sin parámetros
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            # Obtener resultados
            if fetch_one:
                result = cursor.fetchone()
            else:
                result = cursor.fetchall()

            # Convertir automáticamente LOBs a texto/bytes completos
            def _convert_lob_value(value):
                return value.read() if isinstance(value, oracledb.LOB) else value

            if result:
                if fetch_one:
                    result = tuple(_convert_lob_value(v) for v in result)
                else:
                    result = [tuple(_convert_lob_value(v) for v in row) for row in result]
            
            return result
            
        except oracledb.DatabaseError as e:
            logger.error(f"[OCI][ADB] Error al ejecutar SELECT: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def execute_procedure(self, procedure_name: str, params: tuple):
        """
        Ejecuta un procedimiento almacenado de forma segura.
        """
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.callproc(procedure_name, params)
            conn.commit()
        
        except oracledb.DatabaseError as e:
            logger.error(f"[OCI][ADB] Error al ejecutar Procedimiento: {e}")
            raise
        finally:
            if conn:
                conn.close()