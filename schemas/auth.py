"""
Schemas para autenticación de usuarios.
"""
from pydantic import BaseModel

class UserLogin(BaseModel):
    """
    Schema para el login de usuario.
    """
    username: str
    password: str

class Token(BaseModel):
    """
    Schema para el token de acceso.
    """
    access_token: str
    token_type: str
