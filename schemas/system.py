from pydantic import BaseModel, Field
from typing import Optional, List

class DatabaseStatus(BaseModel):
    """Modelo para el estado de la conexión a la base de datos"""
    connected     : bool = Field(..., description="Indica si la conexión está activa")
    database_name : Optional[str] = Field(None, description="Nombre de la base de datos")
    schema_name   : Optional[str] = Field(None, description="Nombre del schema")
    tables        : List[str] = Field(default_factory=list, description="Tablas accesibles")
    views         : List[str] = Field(default_factory=list, description="Vistas accesibles")
    procedures    : List[str] = Field(default_factory=list, description="Procedimientos almacenados accesibles")
    error_message : Optional[str] = Field(None, description="Mensaje de error si hay problemas de conexión")


class OCIStatus(BaseModel):
    """Modelo para el estado de la conexión a OCI"""
    connected     : bool = Field(..., description="Indica si la conexión está activa")
    profile       : str = Field(..., description="Profile de OCI utilizado")
    namespace     : Optional[str] = Field(None, description="Namespace de OCI")
    buckets_accessible : List[str] = Field(default_factory=list, description="Buckets accesibles")
    error_message : Optional[str] = Field(None, description="Mensaje de error si hay problemas de conexión")
