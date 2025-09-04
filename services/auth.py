"""
Servicio de autenticación de usuarios con base de datos Oracle.
"""
import logging
import bcrypt
from typing import Optional, Dict, Any
from database.connection import Connection

logger = logging.getLogger(__name__)

class AuthService:
    """
    Servicio para autenticación de usuarios contra base de datos Oracle.
    """
    
    def __init__(self):
        self.db_connector = Connection()
    
    def _hash_password(self, password: str) -> str:
        """
        Genera un hash bcrypt de la contraseña.
        """
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def _verify_password(self, password: str, hashed_password: str) -> bool:
        """
        Verifica si una contraseña coincide con su hash bcrypt.
        """
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    
    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Autentica un usuario contra la base de datos Oracle.
        
        Args:
            username: Nombre de usuario
            password: Contraseña en texto plano
            
        Returns:
            Dict con información del usuario si la autenticación es exitosa, None en caso contrario
        """
        try:
            # Consulta SQL para obtener el usuario por username
            query = """
                SELECT 
                    user_id,
                    username,
                    email,
                    full_name,
                    password_hash,
                    is_active,
                    created_at
                FROM users 
                WHERE username = :username 
                AND is_active = 1
            """
            
            params = {"username": username}
            result = self.db_connector.execute_select(query, params, fetch_one=True)
            
            if result:
                # Verificar la contraseña usando bcrypt
                stored_password_hash = result[4]  # password_hash está en la posición 4
                
                if self._verify_password(password, stored_password_hash):
                    # Convertir el resultado a un diccionario
                    user_data = {
                        "user_id": result[0],
                        "username": result[1],
                        "email": result[2],
                        "full_name": result[3],
                        "is_active": bool(result[5]),  # is_active ahora está en la posición 5
                        "created_at": result[6]        # created_at ahora está en la posición 6
                    }
                    
                    logger.info(f"[AUTH] Usuario autenticado exitosamente: {username}")
                    return user_data
                else:
                    logger.warning(f"[AUTH] Contraseña incorrecta para usuario: {username}")
                    return None
            else:
                logger.warning(f"[AUTH] Usuario no encontrado: {username}")
                return None
                
        except Exception as e:
            logger.error(f"[AUTH] Error durante la autenticación: {str(e)}")
            return None
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de un usuario por su ID.
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Dict con información del usuario si existe, None en caso contrario
        """
        try:
            query = """
                SELECT 
                    user_id,
                    username,
                    email,
                    full_name,
                    is_active,
                    created_at
                FROM users 
                WHERE user_id = :user_id 
                AND is_active = 1
            """
            
            params = {"user_id": user_id}
            result = self.db_connector.execute_select(query, params, fetch_one=True)
            
            if result:
                return {
                    "user_id": result[0],
                    "username": result[1],
                    "email": result[2],
                    "full_name": result[3],
                    "is_active": bool(result[4]),
                    "created_at": result[5]
                }
            return None
            
        except Exception as e:
            logger.error(f"[AUTH] Error al obtener usuario por ID {user_id}: {str(e)}")
            return None
    
    def create_user(self, username: str, email: str, password: str, full_name: str) -> Optional[int]:
        """
        Crea un nuevo usuario en la base de datos.
        
        Args:
            username: Nombre de usuario
            email: Email del usuario
            password: Contraseña en texto plano
            full_name: Nombre completo
            
        Returns:
            ID del usuario creado si es exitoso, None en caso contrario
        """
        try:
            # Hash de la contraseña
            password_hash = self._hash_password(password)
            
            # Consulta para insertar usuario
            query = """
                INSERT INTO users (username, email, password_hash, full_name, is_active)
                VALUES (:username, :email, :password_hash, :full_name, 1)
                RETURNING user_id INTO :user_id
            """
            
            params = {
                "username": username,
                "email": email,
                "password_hash": password_hash,
                "full_name": full_name,
                "user_id": None
            }
            
            result = self.db_connector.execute_query(query, params, fetch=None)
            
            if result:
                logger.info(f"[AUTH] Usuario creado exitosamente: {username}")
                return result
            else:
                logger.error(f"[AUTH] Error al crear usuario: {username}")
                return None
                
        except Exception as e:
            logger.error(f"[AUTH] Error al crear usuario {username}: {str(e)}")
            return None
