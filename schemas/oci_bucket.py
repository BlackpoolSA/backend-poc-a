from pydantic import BaseModel, Field
from typing import List, Optional

class OCIObjectTypeCounts (BaseModel):
    """Modelo para el conteo de tipos de archivo."""
    pdf       : int = Field(0, description="Número de archivos PDF.")
    csv       : int = Field(0, description="Número de archivos CSV.")
    excel     : int = Field(0, description="Número de archivos Excel (.xls, .xlsx).")
    word      : int = Field(0, description="Número de archivos Word (.doc, .docx).")
    json_file : int = Field(0, description="Número de archivos JSON.")
    other     : int = Field(0, description="Número de otros tipos de archivo.")
    embedding : int = Field(0, description="Número de archivos con embeddings procesados.")

class OCIObjectRAG (BaseModel):
    """Modelo para un objeto (archivo o carpeta) en OCI Object Storage."""
    object_path             : str = Field(..., description="Ruta completa del objeto en el bucket.")
    object_name             : str = Field(..., description="Nombre del objeto.")    
    object_type             : str = Field(..., description="Tipo de objeto: 'file' o 'folder'.")
    object_size             : Optional[int] = Field(None, description="Tamaño del objeto en bytes (solo para archivos).")
    last_modified           : Optional[str] = Field(None, description="Fecha de última modificación.")
    has_embedding           : bool = Field(False, description="Indica si el archivo ya tiene embeddings procesados.")
    file_id                 : Optional[int] = Field(None, description="ID del archivo en la tabla rag_files.")
    file_src_file_name      : Optional[str] = Field(None, description="Nombre del archivo en la tabla rag_files.")
    file_trg_extraction     : Optional[str] = Field(None, description="Contenido extraído del archivo en la tabla rag_files.")
    file_trg_tot_pages      : Optional[int] = Field(None, description="Número de páginas del archivo en la tabla rag_files.")
    file_trg_tot_characters : Optional[int] = Field(None, description="Número de caracteres del archivo en la tabla rag_files.")
    file_trg_tot_time       : Optional[str] = Field(None, description="Tiempo de procesamiento del archivo en la tabla rag_files.")
    file_date               : Optional[str] = Field(None, description="Fecha de creación del archivo en la tabla rag_files.")

class OCIObjectListResponse(BaseModel):
    """Modelo de respuesta para el listado de objetos en un bucket de OCI."""
    bucket_path        : str = Field(..., description="Ruta del bucket consultado.")
    total_objects      : int = Field(..., description="Número total de objetos (archivos y carpetas) encontrados.")
    object_type_counts : OCIObjectTypeCounts  = Field(..., description="Conteo de objectos por tipo.")
    object_rag         : List[OCIObjectRAG] = Field(..., description="Lista de objetos del RAG.")

class TextContentRequest(BaseModel):
    """Modelo para procesar contenido textual directamente."""
    text_content: str = Field(..., description="Contenido textual a procesar (ya procesado por OCR).")
    file_name: str = Field("text_content.txt", description="Nombre del archivo para identificación.")
    file_trg_extraction: Optional[str] = Field(None, description="Contenido extraído del archivo (si ya está disponible).")
    file_trg_tot_pages: Optional[int] = Field(1, description="Número de páginas del documento.")
    file_trg_tot_characters: Optional[int] = Field(None, description="Número de caracteres del documento.")
    file_trg_tot_time: Optional[str] = Field("00:00:00", description="Tiempo de procesamiento del documento.")
    file_trg_language: Optional[str] = Field("esa", description="Idioma del documento.")

class FileUploadRequest(BaseModel):
    """Modelo para subir archivos markdown directamente."""
    file_name: str = Field(..., description="Nombre del archivo markdown.")
    file_content: str = Field(..., description="Contenido del archivo markdown.")
    file_trg_extraction: Optional[str] = Field(None, description="Contenido extraído del archivo (si ya está disponible).")
    file_trg_tot_pages: Optional[int] = Field(1, description="Número de páginas del documento.")
    file_trg_tot_characters: Optional[int] = Field(None, description="Número de caracteres del documento.")
    file_trg_tot_time: Optional[str] = Field("00:00:00", description="Tiempo de procesamiento del documento.")
    file_trg_language: Optional[str] = Field("esa", description="Idioma del documento.")
