"""
Tool for running OCI Select AI queries.
"""
import logging
from database.oci_select_ai import OCISelectAIDB
from core.config import settings

logger = logging.getLogger(__name__)

class OCISelectAITool:
    """Clase para interactuar con el servicio de SELECT AI de OCI."""
    
    def __init__(self):
        self.oci_select_ai_db  = None
        self._initialize_components()

    def _initialize_components(self):
        try:
            self.oci_select_ai_db = OCISelectAIDB()
            logger.info("[TOOL][SELECT_AI] Agente inicializado. [SUCCESS]")
        except Exception as e:
            logger.error(f"[TOOL][SELECT_AI] Error al inicializar Tool: {str(e)}")
            raise

    def oci_select_ai(self, input: str):
        """Generates an explanation for a SQL query using Oracle's SELECT AI service."""
        try:
            narrate = self.oci_select_ai_db.get_tool_response(
                input,
                "OCIPROFILE",
                "narrate",
                "Spanish"
            )

            # Si la narración inicial falla, no tiene sentido continuar.
            if not narrate:
                return "No se pudo generar una narración para la consulta."

            showsql = self.oci_select_ai_db.get_tool_response(
                input,
                "OCIPROFILE",
                "showsql",
                "Spanish"
            )

            # Si no se puede generar el SQL, se devuelve la narración disponible.
            if not showsql:
                return narrate

            explainsql = self.oci_select_ai_db.get_tool_response(
                showsql,
                "OCIPROFILE",
                "explainsql",
                "Spanish"
            )

            if explainsql:
                # Agregar tres saltos de línea antes de cada "```sql" y "##"
                explainsql = explainsql.replace("```sql", "\n\nQuery:\n\n```sql\n").replace("##", "\n\n").replace("-", "\n-").replace("; ```", "; \n```")
            else:
                return showsql

            content = f"""Narrate:\n\n{narrate}\n\nExplainSQL: {explainsql}
"""

            return content
        
        except ValueError as e:
            logger.error(f"[TOOL][SELECT_AI] Error al procesar la consulta: {e}")
            # Relanzar la excepción para que sea manejada por el ToolNode de LangGraph
            raise
        except Exception as e:
            logger.error(f"[TOOL][SELECT_AI] Error inesperado en Select AI: {str(e)}", exc_info=True)
            # Relanzar también los errores inesperados
            raise