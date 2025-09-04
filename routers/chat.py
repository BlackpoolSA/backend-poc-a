"""
Router para el sistema de chat con RAG.
"""
import json
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, status, Form, File, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.security import security_authenticate_user
from services.chat import chat
from fastapi.responses import StreamingResponse
from utils.utils import Utils

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()
utils = Utils()

def get_available_tools() -> List[dict]:
    """Obtiene la lista de herramientas de agente disponibles para la interfaz de chat.

    Estas herramientas se identifican con el prefijo '@' y se utilizan para invocar
    funcionalidades específicas del agente directamente desde la entrada del usuario.
    La lista generada se consume en el frontend para funcionalidades como el
    autocompletado de comandos.

    Returns:
        List[dict]: Una lista de diccionarios, donde cada uno describe una herramienta
                    con su comando, nombre, descripción y un ejemplo de uso.
    """
    return [
        {
            "command": "@select_ai_tool",
            "name": "Select AI Tool",
            "description": "Consultas de base de datos y análisis de datos",
            "example": "¿Cuántos usuarios hay en la tabla users?"
        },
        {
            "command": "@rag_tool", 
            "name": "RAG Tool",
            "description": "Búsqueda en documentos y archivos RAG",
            "example": "Busca información sobre contratos"
        }
    ]

@router.get(
    "/tools",
    summary="Obtener herramientas disponibles",
    description="Lista de herramientas disponibles para autocompletado en el chat",
    tags=["Chat"]
)
def get_tools_endpoint():
    """Endpoint para obtener las herramientas disponibles para autocompletado."""
    return {"tools": get_available_tools()}

@router.post(
    "/query",
    summary="Realizar consulta de chat con streaming",
    description="Procesa una consulta de chat con streaming en tiempo real usando el sistema RAG",
    tags=["Chat"]
)
async def chat_query_endpoint(
    input       : str = Form(..., description="Texto de la consulta del usuario"),
    files_ids   : str = Form("[]", description="IDs de archivos seleccionados para RAG en formato JSON"),
    files       : Optional[List[UploadFile]] = File(None, description="Archivos opcionales adjuntos al chat"),
    credentials : HTTPAuthorizationCredentials = Depends(security)
):
    """Endpoint para consultas de chat con streaming en tiempo real."""
    try:
        security_authenticate_user("/chat/query", credentials)

        # Procesar archivos si se proporcionaron (legacy). Para RAG normalizamos por files_ids
        files_processed, files_metadata = await utils.process_uploaded_files(files or [])
        
        if files_processed:
            logger.info(f"[CHAT][QUERY][ATTACH] {len(files_processed)} archivos. [SUCCESS]")

        # Parsear files_ids desde JSON string
        files_ids_list = json.loads(files_ids) if files_ids else []

        # Preparar request para el agente
        agent_request = {
            "input"     : input,
            "files_ids" : files_ids_list,
            "attch"     : files_metadata
        }

        # Procesar con streaming del chat
        logger.info(f"[CHAT][QUERY] Iniciando LangGraph: [docs={len(files_ids_list)}] [attach={len(files_processed)} [START]")
        
        async def generate_stream():
            async for chunk in chat(agent_request):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )

    except Exception as e:
        logger.error(f"[CHAT][QUERY] Error en streaming: {input}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en streaming: {str(e)}"
        )

@router.post(
    "/query-simple",
    summary="Realizar consulta de chat simple con streaming",
    description="Procesa una consulta de chat con streaming en tiempo real usando el sistema RAG sin archivos adjuntos",
    tags=["Chat"]
)
async def chat_query_simple_endpoint(
    input       : str = Form(..., description="Texto de la consulta del usuario"),
    files_ids   : str = Form("[]", description="IDs de archivos seleccionados para RAG (puede ser entero o array JSON)"),
    credentials : HTTPAuthorizationCredentials = Depends(security)
):
    """Endpoint para consultas de chat simples con streaming en tiempo real (sin archivos adjuntos)."""
    try:
        security_authenticate_user("/chat/query-simple", credentials)

        # Parsear files_ids desde JSON string o entero
        try:
            if files_ids and files_ids.strip():
                if files_ids.startswith('[') and files_ids.endswith(']'):
                    # Es un array JSON
                    files_ids_list = json.loads(files_ids)
                elif files_ids.isdigit():
                    # Es un entero individual
                    files_ids_list = [int(files_ids)]
                else:
                    # Intentar parsear como JSON, si falla, tratar como entero
                    try:
                        files_ids_list = json.loads(files_ids)
                    except json.JSONDecodeError:
                        files_ids_list = [int(files_ids)]
                logger.info(f"[CHAT][QUERY-SIMPLE] files_ids parseados: {files_ids_list}")
            else:
                files_ids_list = []
        except Exception as e:
            logger.warning(f"[CHAT][QUERY-SIMPLE] Error parseando files_ids '{files_ids}': {str(e)}, usando lista vacía")
            files_ids_list = []

        # Preparar request para el agente
        agent_request = {
            "input"     : input,
            "files_ids" : files_ids_list,
            "attch"     : []  # Sin archivos adjuntos
        }

        # Procesar con streaming del chat
        logger.info(f"[CHAT][QUERY-SIMPLE] Iniciando LangGraph: [docs={len(files_ids_list)}] [START]")
        
        async def generate_stream():
            async for chunk in chat(agent_request):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )

    except Exception as e:
        logger.error(f"[CHAT][QUERY-SIMPLE] Error en streaming: {input}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en streaming: {str(e)}"
        )
