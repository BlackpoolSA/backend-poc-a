import json
import logging
from datetime import datetime

from services.tools.oci_rag_tool import OCIRAGTool
from services.tools.oci_select_ai_tool import OCISelectAITool
from langchain_core.tools import tool
from typing import Annotated
from deepagents.state import DeepAgentState
from langgraph.prebuilt import InjectedState

from deepagents import create_deep_agent

from core.config import settings
from utils.utils import Utils
from services.deepagents.streamer import AgentStreamer

# Reconstruir el modelo Pydantic para evitar el error de clase no definida
from langchain_core.caches import BaseCache
from langchain_core.callbacks.manager import Callbacks
from langchain_openai import ChatOpenAI

# Reconstruir el modelo Pydantic para evitar el error de clase no definida
ChatOpenAI.model_rebuild(_types_namespace={"BaseCache": BaseCache, "Callbacks": Callbacks})

logger = logging.getLogger(__name__)

utils = Utils()

class AgentService:
    """
    Servicio principal para el chat con capacidades RAG y SELECT AI.
    Maneja la inicialización de componentes de manera diferida.
    """

    def __init__(self):
        self._vector_search_instance = None
        self._llm = None
        self._prompts = None
        self._agent = None
        self._initialized = False
        # IDs de archivos seleccionados para RAG en la llamada actual
        self._current_files_ids: list[int] = []
    
    def _initialize_components(self):            
        try:
            self._vector_search_instance = OCIRAGTool()
            
            self._llm = ChatOpenAI(
                 model    = settings.GATEWAY_OPENAI_MODEL,
                 api_key  = settings.GATEWAY_OPENAI_API_KEY,
                 base_url = settings.GATEWAY_BASE_URL
            )
            # Establecer la ruta de los prompts
            self._prompts = "backend/services/prompts"
            
            # Construir el grafo de LangGraph
            self._build_agent()

            self._initialized = True
            logger.info("[CHAT][DEEP_AGENT] Componentes inicializados [SUCCESS]")
            
        except Exception as e:
            logger.error(f"[CHAT][DEEP_AGENT] Error inicializando componentes: {str(e)}")
            raise

    def _build_agent(self):

        @tool("rag_tool")
        def call_rag(query: str, state: Annotated[DeepAgentState, InjectedState]) -> str:
            """
            @rag_tool — Buscar y citar conocimiento en documentos cargados (RAG).

            ÚSALA CUANDO:
            - La pregunta requiera contenido de archivos/documents cargados o de la base vectorial.
            - El usuario mencione documentos, PDFs, contratos, manuales, políticas, reportes, o pida “¿qué dice X?”.
            - Se pida resumen, comparación o cita textual de documentos.

            NO LA USES CUANDO:
            - La tarea principal sea generar/entender SQL, esquemas o metadata de tablas (usa @select_ai_tool).
            - La pregunta sea puramente conversacional sin referencia a documentos ni necesidad de evidencia.

            ENTRADA:
            - query (str): pregunta natural. Los IDs de archivos vigentes ya están disponibles en la sesión
            (no los pases aquí). Si no hay archivos, intenta con la base vectorial global.

            SALIDA ESPERADA:
            - Texto breve en markdown con puntos clave y, si es posible, citas/IDs de fragmentos.
            Si no hay resultados, devuelve un mensaje claro como: "NO_MATCH: no se hallaron pasajes relevantes".

            PALABRAS CLAVE DISPONIBLES (solo como indicios, no obligatorias):
            - "documento", "archivo", "pdf", "anexo", "contrato", "manual", "política", "según el documento".

            EJEMPLOS:
            - "¿Qué dice el contrato sobre la cláusula de renovación?" → @rag_tool
            - "Resume el PDF de seguridad y dame los riesgos principales." → @rag_tool
            - "Haz un JOIN entre clientes y ventas por mes." → NO uses @rag_tool (usa @select_ai_tool).
            """
            if not query:
                return "Error: La consulta para la herramienta RAG no puede estar vacía."
            return self._vector_search_instance.oci_vector_search(query, self._current_files_ids)


        # Leer los prompts de los sub-agentes
        _1_AUDIT_LEGAL_FORMS_AGENT_PROMPT_MD = utils.read_file_content(f"{self._prompts}/sub_agents/1_AUDIT_LEGAL_FORMS_AGENT.md")
        _2_AUDIT_RUT_VALIDATION_AGENT_PROMPT_MD = utils.read_file_content(f"{self._prompts}/sub_agents/2_AUDIT_RUT_VALIDATION_AGENT.md")
        _3_AUDIT_PATIENT_DATA_MATCH_AGENT_PROMPT_MD = utils.read_file_content(f"{self._prompts}/sub_agents/3_AUDIT_PATIENT_DATA_MATCH_AGENT.md")
        _4_AUDIT_CONSISTENT_ID_NUMBER_AGENT_MD = utils.read_file_content(f"{self._prompts}/sub_agents/4_AUDIT_CONSISTENT_ID_NUMBER_AGENT.md")
        _5_AUDIT_PAYER_ADRES_AGENT_PROMPT_MD = utils.read_file_content(f"{self._prompts}/sub_agents/5_AUDIT_PAYER_ADRES_AGENT.md")

        # Crear los sub-agentes
        _1_AUDIT_LEGAL_FORMS_AGENT = {
            "name"        : "1_AUDIT_LEGAL_FORMS_AGENT",
            "description" : "Validación de Formularios Legales Obligatorios.",
            "prompt"      : _1_AUDIT_LEGAL_FORMS_AGENT_PROMPT_MD,
        }
        _2_AUDIT_RUT_VALIDATION_AGENT = {
            "name"        : "2_AUDIT_RUT_VALIDATION_AGENT",
            "description" : "Validación de RUT (Vigencia y Existencia)",
            "prompt"      : _2_AUDIT_RUT_VALIDATION_AGENT_PROMPT_MD,
        }
        _3_AUDIT_PATIENT_DATA_MATCH_AGENT = {
            "name"        : "3_AUDIT_PATIENT_DATA_MATCH_AGENT",
            "description" : "Validación de Coincidencia de Datos del Paciente",
            "prompt"      : _3_AUDIT_PATIENT_DATA_MATCH_AGENT_PROMPT_MD,
        }
        _4_AUDIT_CONSISTENT_ID_NUMBER_AGENT = {
            "name"        : "4_AUDIT_CONSISTENT_ID_NUMBER_AGENT",
            "description" : "Validación de Consistencia de Documento del Paciente",
            "prompt"      : _4_AUDIT_CONSISTENT_ID_NUMBER_AGENT_MD,
        }
        _5_AUDIT_PAYER_ADRES_AGENT = {
            "name"        : "5_AUDIT_PAYER_ADRES_AGENT",
            "description" : "Validación de Pagador (ADRES)",
            "prompt"      : _5_AUDIT_PAYER_ADRES_AGENT_PROMPT_MD,
        }
        
        # Leer el prompt del agente principal
        _INSTRUCTIONS_MD = utils.read_file_content(f"{self._prompts}/INSTRUCTIONS.md")

        # Crear el agente con herramientas internas (sin tools adicionales)
        self._agent = create_deep_agent(
            tools        = [],
            instructions = _INSTRUCTIONS_MD,
            model        = self._llm,
            subagents    = [_1_AUDIT_LEGAL_FORMS_AGENT
                            ,_2_AUDIT_RUT_VALIDATION_AGENT
                ]
        ).with_config({"recursion_limit": 1000})


    def get_agent(self):
        """Obtiene el agente compilado, inicializando si es necesario."""
        if not self._initialized:
            self._initialize_components()
            self._build_agent()
            
        return self._agent


# Instancia global del servicio
agent_service = AgentService()

async def agent(payload: dict):
    """
    Punto de entrada usado por el router para ejecutar el agente con streaming.
    Compatible con Deep Agents UI y router actual.
    """
    files = payload.get("files", {})
    
    if not files:
        yield {
            "type": "error",
            "name": "validation",
            "message": "Se requieren archivos para procesar.",
            "comment": "validación fallida",
            "timestamp": datetime.now().isoformat()
        }
        return
        
    # Obtener el agente (se inicializa automáticamente si es necesario)
    agent_instance = agent_service.get_agent()
    
    # Preparar input para DeepAgents
    user_input = payload.get("input") or "Ejecutar tareas asignadas y devolver solo el resultado final."
    agent_input = {
        "messages": [{"role": "user", "content": user_input}],
        "files": files
    }
    
    logger.info(f"[DEEP_AGENT][STREAM] Iniciando procesamiento de {len(files)} archivos [START]")        
    
    # Instanciar nuestro streamer con la instancia del agente
    streamer = AgentStreamer(agent_instance)

    # Usar el método stream de nuestra clase
    async for chunk in streamer.stream(agent_input):
        yield f"data: {json.dumps(chunk)}\n\n"

