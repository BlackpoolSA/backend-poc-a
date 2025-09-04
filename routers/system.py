"""
API para endpoints de sistema y estado.
"""
import logging
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.config import settings
from utils.jwt import verify_jwt_token
from utils.jwt import create_jwt_token

import asyncio
from fastapi.responses import StreamingResponse
from collections import deque
from services.oci_status import OCIStatusChecker

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()

@router.get(
    "/",
    summary="Endpoint Raíz",
    description="Muestra información básica de la API.",
    tags=["Sistema"]
)
async def root():
    return {
        "message": settings.API_TITLE,
        "version": settings.API_VERSION,
        "status": "operativo",
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get(
    "/health",
    summary="Health Check",
    description="Verifica el estado de salud del sistema.",
    tags=["Sistema"]
)
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.API_VERSION
    }

@router.get(
    "/public/status_bucket",
    summary="Estado público de la conexión a OCI Bucket",
    description="Verifica públicamente el estado de la conexión a OCI Object Storage.",
    tags=["Sistema"]
)
async def get_public_bucket_status():
    try:
        checker = OCIStatusChecker()
        status_result = checker.get_oci_connection_status()
        if not status_result.get("connected"):
            raise HTTPException(status_code=503, detail=status_result)
        return status_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/public/status_atp",
    summary="Estado público de la conexión a ATP",
    description="Verifica públicamente el estado de la conexión a la Autonomous Database.",
    tags=["Sistema"]
)
async def get_public_atp_status():
    try:
        checker = OCIStatusChecker()
        # Ejecutar con un timeout de 5 segundos
        status_result = await asyncio.wait_for(
            checker.get_database_status_async(),
            timeout=5.0
        )
        if not status_result.get("connected"):
            # Si la función devuelve un error de conexión, lo propagamos como 503
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=status_result)
        return status_result
    except asyncio.TimeoutError:
        logger.error("[OCI][SYS] Timeout al verificar el estado de la ATP.")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="La verificación del estado de la base de datos ha superado el tiempo de espera."
        )
    except Exception as e:
        logger.error(f"[OCI][SYS] Error inesperado al verificar ATP: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

async def log_generator(log_file_path: str, replay: int = 0):
    """Generador que lee y emite nuevas líneas de un archivo de log.
    Si 'replay' > 0, envía también las últimas 'replay' líneas ya existentes al conectarse.
    """
    try:
        with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
            # Enviar historial reciente si se solicitó
            if replay and replay > 0:
                try:
                    last_lines = deque(f, maxlen=int(replay))
                    for line in last_lines:
                        clean_line = line.strip().replace('\n', '').replace('\r', '')
                        if clean_line:
                            yield f"data: {clean_line}\n\n"
                except Exception:
                    pass

            # Ir al final y transmitir en vivo
            f.seek(0, 2)
            while True:
                line = f.readline()
                if not line:
                    await asyncio.sleep(1)
                    continue
                clean_line = line.strip().replace('\n', '').replace('\r', '')
                yield f"data: {clean_line}\n\n"
    except Exception as e:
        logger.error(f"[SYS] Error abriendo archivo de log: {e}")
        yield f"data: Error al abrir archivo de log: {e}\n\n"

@router.get("/logs/stream", summary="Log de Procesamiento", tags=["Sistema"])
async def stream_logs(token: str = Query(None), replay: int = Query(200)):
    if not token:
        raise HTTPException(status_code=401, detail="Token no proporcionado")

    user_payload = verify_jwt_token(token)
    if not user_payload:
        raise HTTPException(status_code=401, detail="Token de autenticación inválido o expirado")
    
    log_file_path = "audit.log"
    
    if not os.path.exists(log_file_path):
        try:
            with open(log_file_path, "w", encoding="utf-8") as f:
                f.write(f"# Log iniciado - {datetime.utcnow().isoformat()}\n")
        except Exception as e:
            logger.error(f"[SYS] Error creando archivo de log: {e}")
    
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "text/event-stream; charset=utf-8"
    }
    
    return StreamingResponse(log_generator(log_file_path, replay=replay), media_type="text/event-stream", headers=headers)

@router.post(
    "/jwt/refresh",
    summary="Refrescar token JWT",
    description=(
        "Emite un nuevo token JWT a partir de uno vigente, extendiendo su expiración. "
        "Solo funciona si el token actual NO ha expirado."
    ),
    tags=["Sistema"]
)
async def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Refresca un token vigente renovando su expiración.

    - Requiere Authorization: Bearer <token>
    - Copia el payload actual excluyendo las claims de tiempo y reemite un nuevo token
    """
    user_payload = verify_jwt_token(credentials.credentials)
    if not user_payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de autenticación inválido o expirado")

    # Excluir claims de control temporal que serán regeneradas
    payload_copy = {k: v for k, v in user_payload.items() if k not in {"iat", "nbf", "exp"}}

    issued_at = datetime.utcnow()
    expires_at = issued_at + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    token = create_jwt_token(payload_copy)
    if not token:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo refrescar el token")

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        "issued_at": issued_at.strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
    }

@router.post(
    "/jwt/dev",
    summary="Emitir token de desarrollo",
    description=(
        "Emite un token JWT para entornos de desarrollo. "
        "Requiere que AUTH_DEV_TOKEN_ENABLED sea True y, opcionalmente, una X-Dev-Key."
    ),
    tags=["Sistema"]
)
async def issue_dev_token(request: Request, user_id: str = "dev-user"):
    if not settings.AUTH_DEV_TOKEN_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Emisión de token de desarrollo está deshabilitada."
        )

    dev_key_required = settings.AUTH_DEV_TOKEN_DEV_KEY
    if dev_key_required and request.headers.get("X-Dev-Key") != dev_key_required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El valor del encabezado 'X-Dev-Key' es incorrecto o no fue proporcionado."
        )

    issued_at = datetime.utcnow()
    expires_at = issued_at + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    token = create_jwt_token({
        "user_id": user_id,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp())
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        "issued_at": issued_at.strftime("%Y-%m-%d %H:%M:%S"),
        "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S")
    }


@router.post(
    "/jwt/prod",
    summary="Emitir token de producción",
    description=(
        "Emite un token JWT para producción mediante client credentials. "
        "Requiere que AUTH_PROD_TOKEN_ENABLED sea True."
    ),
    tags=["Sistema"]
)
async def issue_prod_token(client_id: str, client_secret: str, user_id: str = "api-user"):
    if not settings.AUTH_PROD_TOKEN_ENABLED:
        raise HTTPException(status_code=403, detail="Emisión de token en producción deshabilitada.")
    
    if client_id != settings.AUTH_CLIENT_ID or client_secret != settings.AUTH_CLIENT_SECRET:
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")

    token = create_jwt_token({"user_id": user_id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES
    }

