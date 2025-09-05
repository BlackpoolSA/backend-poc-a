import os
from typing import Optional, List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Configuración centralizada del sistema.
    Carga las variables desde un archivo .env y las valida.
    El orden y los comentarios de esta clase están alineados con el archivo .env.
    """

    # ============================================================================
    # CONFIGURACIÓN DE LA API
    # ============================================================================
    API_TITLE: str = "ORACLE AI: Depp Agents API"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = "API para el sistema de Agentes de IA"

    # ============================================================================
    # CONFIGURACIÓN DE SEGURIDAD
    # ============================================================================
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ============================================================================
    # CONFIGURACIÓN DE JWT / TOKENS
    # ============================================================================
    # Dev: habilita emisión de tokens en /api/jwt/dev (usar solo en desarrollo)
    AUTH_DEV_TOKEN_ENABLED: bool = True
    # Opcional: si lo defines, debes enviar header X-Dev-Key con este valor
    AUTH_DEV_TOKEN_DEV_KEY: Optional[str] = None
    # Prod: habilita emisión de tokens en /api/jwt/prod (client credentials)
    AUTH_PROD_TOKEN_ENABLED: bool = False
    AUTH_CLIENT_ID: Optional[str] = None
    AUTH_CLIENT_SECRET: Optional[str] = None

    # ============================================================================
    # CONFIGURACIÓN DE LLM (PROXI: OCI Generative AI)
    # ============================================================================
    GATEWAY_BASE_URL: str
    GATEWAY_OPENAI_MODEL: str
    GATEWAY_OPENAI_API_KEY: str

    # ============================================================================
    # HUGGINGFACE TOKEN
    # ============================================================================
    HF_TOKEN: str

    # ============================================================================
    # CONFIGURACIÓN DE LOGGING
    # ============================================================================
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str  = "audit.log"

    # ============================================================================
    # CONFIGURACIÓN DE ORACLE CLOUD INFRASTRUCTURE (OCI)
    # ============================================================================
    OCI_PROFILE: str = "DEFAULT"
    OCI_CONFIG_FILE: str = "oci/config"
    OCI_REGION: Optional[str] = None
    OCI_NAMESPACE: Optional[str] = None
    OCI_DEFAULT_BUCKET: str = "PoCSIA"

    # ============================================================================
    # CONFIGURACIÓN DE ORACLE AUTONOMOUS DATABASE (ATP23ai)
    # ============================================================================
    CON_ADB_DEV_USER_NAME: str
    CON_ADB_DEV_PASSWORD: str
    CON_ADB_DEV_SERVICE_NAME: str
    CON_ADB_WALLET_LOCATION: str
    CON_ADB_WALLET_PASSWORD: str

    # ============================================================================
    # CONFIGURACIÓN DE OCI GENERATIVE AI
    # ============================================================================
    CON_GEN_AI_SERVICE_ENDPOINT: str
    CON_GEN_AI_EMB_MODEL_ID: str
    CON_GEN_AI_CHAT_MODEL_ID: str
    CON_COMPARTMENT_ID: str
    CON_GEN_AI_CHAT_MODEL_PROVIDER: str

    # ============================================================================
    # CONFIGURACIÓN DE AUDITORÍA MÉDICA
    # ============================================================================
    AUDIT_GLOSAS_FILE_ID: int = 210  # ID del archivo con glosas oficiales en la base vectorial
    
    # ============================================================================
    # CONFIGURACIÓN DE ARCHIVOS TEMPORALES
    # ============================================================================
    TEMP_DIR: str = "temp"
    MAX_TEMP_FILES: int = 100
    TEMP_FILE_RETENTION_HOURS: int = 24

    # ============================================================================
    # CONFIGURACIÓN DE OCR
    # ============================================================================
    OCR_TEMP_DIR: str = "temp"
    OCR_SERVICE_URL: str = "http://159.112.137.0:8001/ocr"
  
    # ============================================================================
    # CONFIGURACIÓN DE ARCHIVOS
    # ============================================================================
    MAX_FILE_SIZE: int = 52428800
    ALLOWED_TYPES: List[str] = [
        "application/pdf",           # PDF
        "application/xml",           # XML
        "text/xml",                  # XML alternativo
        "application/json",          # JSON ← AGREGAR
        "text/json",                 # JSON alternativo ← AGREGAR
        "image/jpeg",                # JPEG
        "image/jpg",                 # JPG
        "image/png",                 # PNG
        "application/x-zip-compressed", # ZIP
        "application/zip"               # ZIP alternativo
    ]  

    class Config:
        env_file = ".env"
        case_sensitive = True


# Instancia global de configuración
settings = Settings()
