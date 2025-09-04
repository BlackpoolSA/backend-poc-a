"""
Servicio OCI Select AI para consultas de inteligencia artificial sobre datos en Oracle Database.
"""
import logging
import pandas as pd

from database.connection import Connection
from core.config import settings

logger = logging.getLogger(__name__)

class OCISelectAIDB:
    """
    Servicio para ejecutar consultas SELECT AI en Oracle Database.
    """
    
    def __init__(self):
        self.db_connector = Connection()
    
    def get_tool_response(
            self,
            prompt,
            profile_name,
            action,
            language
        ):
        """
        Generates a chat response using the Select AI profile.

        Args:
            prompt (str): The user prompt or query.
            profile_name (str): The name of the profile to use.
            action (str): The action to perform.
            language (str): The language for the response.

        Returns:
            str: The generated chat response.
        """ 
        
        # Query con placeholders para parámetros
        query = """
            SELECT
                DBMS_CLOUD_AI.GENERATE(
                prompt       => :prompt,
                profile_name => :profile_name,
                action       => :action) AS CHAT
            FROM DUAL
        """
        
        # Parámetros separados para mayor seguridad
        params = {
            'prompt': f"{prompt} /** Format the response in markdown. Do not underline titles. Just focus on the database tables. Answer in {language}. If you do not know the answer, answer imperatively and exactly: 'NNN.' **/",
            'profile_name': profile_name,
            'action': action
        }
        
        # Usar execute_query con parámetros separados
        result = self.db_connector.execute_select(query, params=params, fetch_one=True)
        logger.info(f"[TOOL][SELECT_AI] action: {action} [SUCCESS]")

        print("--------------------------------")
        val = result[0].read() if hasattr(result[0], 'read') else result[0]
        one_line = ' '.join(str(val).split())
        print(one_line)
        print("--------------------------------")

        # Extraer la columna CHAT del resultado
        return one_line
