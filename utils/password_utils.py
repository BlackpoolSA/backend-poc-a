"""
Utilidades para el manejo de contraseñas con bcrypt.
"""
import bcrypt
import argparse

def hash_password(password: str) -> str:
    """
    Genera un hash bcrypt de la contraseña.
    
    Args:
        password: Contraseña en texto plano
        
    Returns:
        Hash bcrypt de la contraseña
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verifica si una contraseña coincide con su hash bcrypt.
    
    Args:
        password: Contraseña en texto plano
        hashed_password: Hash bcrypt de la contraseña
        
    Returns:
        True si la contraseña coincide, False en caso contrario
    """
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generar hash de contraseña con bcrypt")
    parser.add_argument("password", help="Contraseña a hashear")
    parser.add_argument("--verify", help="Hash para verificar")
    
    args = parser.parse_args()
    
    if args.verify:
        is_valid = verify_password(args.password, args.verify)
        print(f"Contraseña válida: {is_valid}")
    else:
        hashed = hash_password(args.password)
        print(f"Hash de '{args.password}': {hashed}")
        
        # Verificar que funciona
        is_valid = verify_password(args.password, hashed)
        print(f"Verificación: {is_valid}")
