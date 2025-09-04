"""
Router para recuperación de contexto RAG sin procesamiento de LLM.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import List, Optional
import json

from core.security import security_authenticate_user
from services.tools.oci_rag_tool import OCIRAGTool

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()

@router.post(
    "/context",
    summary="Recuperar contexto RAG sin procesamiento de LLM",
    description="Realiza búsqueda vectorial y devuelve solo el contexto relevante sin generar respuesta del LLM",
    tags=["RAG Context"]
)
async def get_rag_context_endpoint(
    input       : str = Form(..., description="Consulta para buscar contexto relevante"),
    files_ids   : str = Form("[]", description="IDs de archivos para filtrar la búsqueda (entero o array JSON)"),
    k           : int = Form(10, description="Número de documentos a recuperar (default: 10, máximo: 50)"),
    credentials : HTTPAuthorizationCredentials = Depends(security)
):
    """Endpoint para recuperar contexto RAG sin procesamiento de LLM."""
    try:
        security_authenticate_user("/rag/context", credentials)

        # Validar y limitar el parámetro k
        k = max(1, min(k, 50))  # Entre 1 y 50

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
                logger.info(f"[RAG][CONTEXT] files_ids parseados: {files_ids_list}")
            else:
                files_ids_list = []
        except Exception as e:
            logger.warning(f"[RAG][CONTEXT] Error parseando files_ids '{files_ids}': {str(e)}, usando lista vacía")
            files_ids_list = []

        # Inicializar herramienta RAG
        rag_tool = OCIRAGTool()
        
        # Obtener contexto con k configurable
        context = rag_tool.oci_vector_search_context_only(input, files_ids_list, k)
        
        logger.info(f"[RAG][CONTEXT] Contexto recuperado: {context['total_documents']} documentos (k={k}) [SUCCESS]")
        
        return context

    except Exception as e:
        logger.error(f"[RAG][CONTEXT] Error recuperando contexto: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error recuperando contexto: {str(e)}"
        )

@router.post(
    "/raw-results",
    summary="Recuperar resultados brutos de búsqueda vectorial",
    description="Realiza búsqueda vectorial y devuelve resultados brutos con scores de similitud",
    tags=["RAG Context"]
)
async def get_raw_search_results_endpoint(
    input       : str = Form(..., description="Consulta para buscar documentos relevantes"),
    files_ids   : str = Form("[]", description="IDs de archivos para filtrar la búsqueda (entero o array JSON)"),
    k           : int = Form(10, description="Número de documentos a recuperar (default: 10, máximo: 50)"),
    credentials : HTTPAuthorizationCredentials = Depends(security)
):
    """Endpoint para recuperar resultados brutos de búsqueda vectorial con scores."""
    try:
        security_authenticate_user("/rag/raw-results", credentials)

        # Validar y limitar el parámetro k
        k = max(1, min(k, 50))  # Entre 1 y 50

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
                logger.info(f"[RAG][RAW-RESULTS] files_ids parseados: {files_ids_list}")
            else:
                files_ids_list = []
        except Exception as e:
            logger.warning(f"[RAG][RAW-RESULTS] Error parseando files_ids '{files_ids}': {str(e)}, usando lista vacía")
            files_ids_list = []

        # Inicializar herramienta RAG
        rag_tool = OCIRAGTool()
        
        # Obtener resultados brutos con k configurable
        results = rag_tool.oci_vector_search_raw_results(input, files_ids_list, k)
        
        logger.info(f"[RAG][RAW-RESULTS] Resultados brutos recuperados: {len(results)} documentos (k={k}) [SUCCESS]")
        
        return {
            "query": input,
            "k_requested": k,
            "total_results": len(results),
            "results": results
        }

    except Exception as e:
        logger.error(f"[RAG][RAW-RESULTS] Error recuperando resultados brutos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error recuperando resultados brutos: {str(e)}"
        )
