import logging
import jwt
from typing import Dict, Optional
from datetime import datetime, timedelta

from core.config import settings

logger = logging.getLogger(__name__)

def verify_jwt_token(token: str) -> Optional[Dict]:
    """
    Verificar y decodificar token JWT
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("[UTL][JWT] Token expirado.")
        return None
    except jwt.InvalidTokenError as e:
        logger.error(f"[UTL][JWT] Error al verificar token: {e}")
        return None


def create_jwt_token(payload: Dict, expires_minutes: Optional[int] = None) -> Optional[str]:
    """
    Crear un token JWT firmado con expiración.
    """
    try:
        to_encode = payload.copy()
        now = datetime.utcnow()
        expire_minutes = expires_minutes if expires_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
        expire = now + timedelta(minutes=expire_minutes)
        
        to_encode.update({
            "iat": now,
            "nbf": now,
            "exp": expire
        })
        
        token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return token
    except Exception as e:
        logger.error(f"[UTL][JWT] Error al crear token: {e}")
        return None