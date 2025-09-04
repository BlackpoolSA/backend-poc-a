"""
Router para la autenticación de usuarios.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from schemas.auth import Token
from utils.jwt import create_jwt_token
from services.auth import AuthService

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post(
    "/token",
    summary="Autenticar usuario",
    description="Autentica a un usuario y devuelve un token de acceso.",
    response_model=Token,
    tags=["Auth"]
)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Endpoint para autenticar usuarios y generar un token.
    """
    try:
        # Crear instancia del servicio de autenticación
        auth_service = AuthService()
        
        # Autenticar usuario contra la base de datos
        user = auth_service.authenticate_user(form_data.username, form_data.password)
        
        if user:
            # Crear un payload para el token con información del usuario
            payload = {
                "sub": user["username"],
                "user_id": user["user_id"],
                "email": user["email"],
                "full_name": user["full_name"]
            }
            
            access_token = create_jwt_token(payload)
            
            if not access_token:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="No se pudo crear el token de acceso",
                )
                
            logger.info(f"[AUTH] Token generado exitosamente para usuario: {user['username']}")
            return {"access_token": access_token, "token_type": "bearer"}
        else:
            logger.warning(f"[AUTH] Intento de autenticación fallido para usuario: {form_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario o contraseña incorrectos",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
    except HTTPException:
        # Re-lanzar excepciones HTTP
        raise
    except Exception as e:
        logger.error(f"[AUTH] Error inesperado durante la autenticación: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor durante la autenticación",
        )
