"""
Agente de chat con LangGraph usando capacidades RAG y SELECT AI.
"""
import logging
import uuid
from typing import Annotated
from datetime import datetime
from copilotkit import CopilotKitState
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate

# Primero importar las dependencias para resolver referencias circulares
from langchain_core.caches import BaseCache
from langchain_core.callbacks.manager import Callbacks
# Luego importar ChatOpenAI
from langchain_openai import ChatOpenAI

# Reconstruir el modelo Pydantic para evitar el error de clase no definida
ChatOpenAI.model_rebuild(_types_namespace={"BaseCache": BaseCache, "Callbacks": Callbacks})

from core.config import settings
from services.tools.oci_rag_tool import OCIRAGTool
from services.tools.oci_select_ai_tool import OCISelectAITool

logger = logging.getLogger(__name__)

class ChatService:
    """
    Servicio principal para el chat con capacidades RAG y SELECT AI.
    Maneja la inicialización de componentes de manera diferida.
    """
    
    def __init__(self):
        self._vector_search_instance = None
        self._select_ai_instance = None
        self._llm = None
        self._graph = None
        self._initialized = False
        # IDs de archivos seleccionados para RAG en la llamada actual
        self._current_files_ids: list[int] = []
    
    def _initialize_components(self):            
        try:
            self._vector_search_instance = OCIRAGTool()
            self._select_ai_instance = OCISelectAITool()
            
            self._llm = ChatOpenAI(
                model    = settings.GATEWAY_OPENAI_MODEL,
                api_key  = settings.GATEWAY_OPENAI_API_KEY,
                base_url = settings.GATEWAY_BASE_URL
            )
            
            # Construir el grafo de LangGraph
            self._build_graph()
            
            self._initialized = True
            logger.info("[CHAT][SERVICE] Componentes inicializados exitosamente [SUCCESS]")
            
        except Exception as e:
            logger.error(f"[CHAT][SERVICE] Error inicializando componentes: {str(e)}")
            raise
    
    def _build_graph(self):
        """Construye el grafo de LangGraph para el agente."""
        
        # --- ESTADO DEL GRAFO SIMPLIFICADO ---
        class AgentState(CopilotKitState):
            messages: Annotated[list, add_messages]

        # --- TOOLS  ---
        @tool("rag_tool")
        def call_rag(query: str) -> str:
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


        @tool("select_ai_tool")
        def call_select_ai(query: str) -> str:
            """
            @select_ai_tool — Redactar/razonar consultas SQL mediante Select AI.

            ÚSALA CUANDO:
            - La pregunta implique obtener datos desde tablas, columnas o vistas (KPIs, joins, filtros).
            - El usuario mencione SQL, SELECT, JOIN, GROUP BY, "tabla", "esquema", "base de datos".
            - Se quiera proponer la consulta SQL a partir de intención de negocio.

            NO LA USES CUANDO:
            - La respuesta está en documentos PDF/Word/etc. (usa @rag_tool).
            - El usuario pide explicación conceptual sin necesidad de datos tabulares.

            ENTRADA:
            - query (str): objetivo en lenguaje natural (qué dato quiere, filtros, agregaciones, rango temporal).
            Si el usuario especifica esquema/BD, inclúyelo en el prompt de salida.

            SALIDA ESPERADA:
            - SQL válido y conciso + notas de supuestos (si faltan columnas exactas).
            Si faltan detalles críticos, devuelve una consulta con TODOs o asunciones explícitas.

            EJEMPLOS:
            - "Ventas totales por mes 2024 y top 5 categorías" → @select_ai_tool
            - "¿Qué dice el PDF de seguridad?" → NO uses @select_ai_tool (usa @rag_tool).
            """
            if not query:
                return "Error: La consulta para la herramienta Select AI no puede estar vacía."
            return self._select_ai_instance.oci_select_ai(query)

        # Vincular herramientas al LLM
        tools = [call_rag, call_select_ai]
        llm_with_tools = self._llm.bind_tools(tools)
        
        policy = """
        Eres un agente con dos herramientas: @rag_tool y @select_ai_tool.
        - Si la pregunta exige evidencia en documentos, usa @rag_tool.
        - Si la pregunta requiere SQL/tablas/joins/KPIs, usa @select_ai_tool.
        - Si ambas aportan valor, llama a ambas (en cualquier orden) y luego responde combinando resultados.
        Responde en español, claro y conciso.
        """

        prompt = ChatPromptTemplate.from_messages([
            ("system", policy),
            ("placeholder", "{messages}")
        ])

        chain = prompt | llm_with_tools

        # Construir el grafo con el estado simplificado
        agent_builder = StateGraph(AgentState)

        # Nodos del grafo
        agent_builder.add_node(
        "agent",
        lambda state: {"messages": [chain.invoke({"messages": state["messages"]})]}
        )
        agent_builder.add_node("tools", ToolNode(tools))

        # Conexiones del grafo
        agent_builder.add_edge("tools", "agent")
        agent_builder.add_conditional_edges(
            "agent", tools_condition
        )
        agent_builder.set_entry_point("agent")

        # Compilar
        self._graph = agent_builder.compile()

    def get_graph(self):
        """Obtiene el grafo compilado, inicializando si es necesario."""
        if not self._initialized:
            self._initialize_components()
        return self._graph

# Instancia global del servicio
chat_service = ChatService()

async def chat(payload: dict):
    """
    Punto de entrada usado por el router para ejecutar el agente con streaming.
    """
    try:
        # Preparar el input del usuario
        user_input = payload.get("input", "")
        if not user_input:
            # Enviar un evento de error si no hay input (esquema estandarizado)
            yield {
                "type"      : "error",
                "name"      : "validation",
                "message"   : "El input no puede estar vacío.",
                "comment"   : "validación fallida",
                "timestamp" : datetime.now().isoformat()
            }
            return
            
        # Capturar files_ids para RAG (desde payload['files_ids'])
        files_ids = [int(fid) for fid in (payload.get("files_ids") or []) if fid]

        # Guardar en el servicio para que lo lea la tool RAG
        chat_service._current_files_ids = files_ids

        # El estado inicial solo necesita los mensajes
        inputs = {"messages": [HumanMessage(content=user_input)]}
        config = {"configurable": {"thread_id": f"thread-{uuid.uuid4()}"}}
        
        # Obtener el grafo del servicio (se inicializa automáticamente si es necesario)
        graph = chat_service.get_graph()
        
        # Procesar streaming de chunks para enviar eventos detallados
        async for chunk in graph.astream(inputs, config):
            logger.info(f"[CHAT][STREAM] Chunk: {chunk}")

            # Extraer el último mensaje del chunk
            if "agent" in chunk:
                message = chunk["agent"]['messages'][-1]
                # Evento: El agente decide llamar a una herramienta
                if message.tool_calls:
                    # Si ya decidió herramientas, tomamos la primera para un comentario breve
                    tool_name = None
                    try:
                        tool_name = (message.tool_calls[0].get("name") if isinstance(message.tool_calls, list) and message.tool_calls else None)
                    except Exception:
                        tool_name = None
                    yield {
                        "type"      : "agent_processing",
                        "name"      : "agent",
                        "message"   : "Analizando consulta...",
                        "comment"   : (f"@{tool_name} está procesando la solicitud…" if tool_name else "Analizando…"),
                        "timestamp" : datetime.now().isoformat()
                    }
                # Evento: El agente genera la respuesta final
                elif message.content:
                    yield {
                        "type"      : "ai_response",
                        "name"      : "assistant",
                        "message"   : message.content,
                        "comment"   : "Respuesta final.",
                        "timestamp" : datetime.now().isoformat()
                    }

            # Evento: La(s) herramienta(s) devuelve(n) resultado(s)
            elif "tools" in chunk:
                messages = chunk["tools"].get('messages', []) or []
                
                # Emitir un evento por cada ToolMessage recibido, preservando el orden
                for msg in messages:
                    yield {
                        "type"      : "tool_result",
                        "name"      : getattr(msg, 'name', None) or getattr(msg, 'tool_name', None) or 'tool',
                        "message"   : getattr(msg, 'content', '') or getattr(msg, 'message', ''),
                        "comment"   : f"Resultado de @{getattr(msg, 'name', None) or getattr(msg, 'tool_name', None) or 'tool'}.",
                        "timestamp" : datetime.now().isoformat()
                    }

                    yield {
                        "type"      : "tool_result",
                        "name"      : "tool",
                        "message"   : str(msg),
                        "comment"   : "Resultado de herramienta.",
                        "timestamp" : datetime.now().isoformat()
                    }

    except Exception as e:
        logger.error(f"[CHAT][AGENT] Error en streaming del agente: {str(e)}")
        yield {
            "type"      : "error",
            "name"      : "agent",
            "message"   : f"Error en el agente: {str(e)}",
            "comment"   : "error en ejecución",
            "timestamp" : datetime.now().isoformat()
        }