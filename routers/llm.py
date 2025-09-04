"""
Router LLM: Micro-proxy estilo OpenAI (/v1/chat/completions) hacia OCI Generative AI.

Uso: clientes OpenAI (p.ej. langchain_openai.ChatOpenAI) apuntando a `base_url=/llm/v1`.
Autenticación: JWT o API-KEY igual a `settings.GATEWAY_OPENAI_API_KEY`.
Streaming: deshabilitado.
"""
import logging
import time
import json
import os
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, status, Body
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import settings
from utils.jwt import verify_jwt_token
from services.oci_bucket import OCIClient

# Resolver dependencias pydantic de LangChain antes de importar ChatOCIGenAI
from langchain_core.caches import BaseCache
from langchain_core.callbacks.manager import Callbacks
from langchain_community.chat_models import ChatOCIGenAI

# Reconstruir modelo para evitar errores de clases no definidas
ChatOCIGenAI.model_rebuild(_types_namespace={"BaseCache": BaseCache, "Callbacks": Callbacks})

logger = logging.getLogger(__name__)
router = APIRouter()
# Permitir manejar auth personalizada (JWT o API-KEY) sin lanzar 403 automático
security = HTTPBearer(auto_error=False)




def _build_openai_like_response(model: str, content: str, usage: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Mapea contenido a la estructura OpenAI Chat Completions (no streaming)."""
    return {
        "id": "chatcmpl-oci",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": usage or {},
    }


def _ensure_oci_config() -> None:
    """Valida configuración OCI utilizando el cliente estándar del proyecto (OCIClient)."""
    # Instanciar asegura lectura de perfil/archivo y lanza si algo falta
    OCIClient()


def _authorize(credentials: Optional[HTTPAuthorizationCredentials], api_name: str) -> None:
    """Autoriza por JWT o API-KEY del gateway y registra en logs el acceso."""
    token = credentials.credentials if credentials else None
    is_jwt_ok = False
    if token:
        try:
            user_payload = verify_jwt_token(token)
            if user_payload:
                is_jwt_ok = True
                logger.info(
                    f"[OCI][JWT][API] Name: [{api_name}] Usuario: [{user_payload.get('user_id','unknown')}] [SUCCESS]"
                )
        except Exception:
            is_jwt_ok = False

    if not is_jwt_ok:
        if not token or token != settings.GATEWAY_OPENAI_API_KEY:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de autenticación inválido o expirado")
        logger.info(f"[LLM][APIKEY] Acceso con API-KEY de gateway [{api_name}] [SUCCESS]")


def _mask(value: Optional[str], keep: int = 6) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "***"


@router.post(
    "/v1/chat/completions",
    summary="OpenAI-compatible Chat Completions",
    description="Traduce solicitudes OpenAI a OCI GenAI (chat) y retorna respuesta estilo OpenAI. Streaming deshabilitado.",
    tags=["LLM Gateway"],
)
def chat_completions(
    payload: Dict[str, Any] = Body(...),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Endpoint no-stream. Si payload.stream=True, responde como no-stream por compatibilidad básica."""
    try:
        _authorize(credentials, "/llm/v1/chat/completions")

        # Asegurar configuración OCI válida
        _ensure_oci_config()

        # Preparar parámetros de modelo
        model = payload.get("model")
        temperature = payload.get("temperature", 0.7)
        max_tokens = payload.get("max_tokens", 1024)

        model_id = settings.CON_GEN_AI_CHAT_MODEL_ID

        # Inicializar LLM de OCI vía LangChain (no stream)
        llm = ChatOCIGenAI(
            model_id         = model_id,
            service_endpoint = settings.CON_GEN_AI_SERVICE_ENDPOINT,
            compartment_id   = settings.CON_COMPARTMENT_ID,
            provider         = settings.CON_GEN_AI_CHAT_MODEL_PROVIDER,
            is_stream        = False,
            auth_type        = "API_KEY",
            auth_profile     = settings.OCI_PROFILE,
            model_kwargs = {
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

        # Construir prompt a partir de mensajes OpenAI
        messages: List[Dict[str, Any]] = payload.get("messages", [])
        if messages:
            # Concatenar chat en un único prompt simple (compatibilidad amplia)
            prompt_parts = []
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                prompt_parts.append(f"{role}: {content}")
            prompt = "\n".join(prompt_parts)
        else:
            prompt = payload.get("prompt") or ""

        logger.info(f"[LLM][REQ] lc_chat model_id={model_id} temp={temperature} max_tokens={max_tokens} preview={prompt[:200]}")

        try:
            result = llm.invoke(prompt)
            content = str(result)
        except Exception as e:
            logger.error(f"[LLM][OCI][ERROR] LangChain/OCI invocation failed: {e}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error en servicio OCI GenAI")

        return _build_openai_like_response(model=model or model_id, content=content, usage={})

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[LLM][GATEWAY] Error procesando solicitud: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno en gateway LLM")


