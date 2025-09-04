from pydantic import BaseModel, Field
from typing import Optional

class RAGFilesShema(BaseModel):
    """Modelo de la tabla RAG_FILES."""
    file_id             : Optional[int] = Field(None, description="ID del archivo.")
    module_id           : int = Field(..., description="ID del módulo.")
    file_src_file_name  : str = Field(..., description="Nombre del archivo fuente.")
    file_src_size       : int = Field(0, description="Tamaño del archivo fuente en bytes.")
    file_src_strategy   : str = Field('None', description="Estrategia de procesamiento utilizada para el archivo fuente.")
    file_trg_obj_name   : Optional[str] = Field('None', description="Nombre del archivo procesado/extraído.")
    file_trg_extraction : Optional[str] = Field(None, description="Contenido extraído del archivo (puede ser texto largo).")
    file_trg_tot_pages  : int = Field(1, description="Número total de páginas procesadas.")
    file_trg_tot_characters : int = Field(0, description="Número total de caracteres extraídos.")
    file_trg_tot_time   : str = Field('00:00:00', description="Tiempo total de procesamiento (formato HH:MM:SS).")
    file_trg_language   : str = Field('esa', description="Idioma detectado o procesado (código ISO).")
    file_trg_pii        : int = Field(0, description="Indicador de presencia de PII (información personal identificable).")
    file_description    : str = Field(..., description="Descripción del archivo.")
    file_version        : int = Field(1, description="Versión del archivo.")
    file_state          : int = Field(1, description="Estado del archivo (1=activo, 0=inactivo, etc).")
    file_date           : Optional[str] = Field(None, description="Fecha de creación o procesamiento del archivo (timestamp).")