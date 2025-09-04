"""
Módulo de seguridad para autenticación JWT y validación de tokens.
"""
import logging
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from utils.jwt import verify_jwt_token

logger = logging.getLogger(__name__)

def security_authenticate_user(
    api_name    : str,
    credentials : HTTPAuthorizationCredentials,
    user_id_key : str = "user_id"
) -> None:
    """
    Autentica a un usuario verificando su token JWT.

    Args:
        api_name: Nombre de la API para logging (ej: "/oci/bucket/list")
        credentials: Credenciales HTTP Bearer con el token JWT
        user_id_key: Clave para extraer el user_id del payload (default: "user_id")

    Raises:
        HTTPException: Si el token es inválido o expirado
    """
    user_payload = verify_jwt_token(credentials.credentials)
    if not user_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación inválido o expirado"
        )

    user_id = user_payload.get(user_id_key, "unknown")
    logger.info(f"[OCI][JWT][API] Name: [{api_name}] Usuario: [{user_id}] [SUCCESS]")
