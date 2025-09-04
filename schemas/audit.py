"""
Schemas para el servicio de auditoría médica
"""
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum

class AuditResponse(str, Enum):
    """Posibles respuestas de auditoría"""
    CUMPLE = "Cumple"
    NO_CUMPLE = "No cumple"

class AuditDecision(str, Enum):
    """Decisiones finales de auditoría"""
    APROBADA_TOTAL = "Aprobada total"
    APROBADA_PARCIAL = "Aprobada parcial"
    DEVUELTA = "Devuelta"
    ANULADA = "Anulada"

class AuditType(str, Enum):
    """Tipos de auditoría especializada"""
    FACTURA = "factura"
    HISTORIA_CLINICA = "historia_clinica"
    MEDICAMENTOS = "medicamentos"
    EXAMENES = "examenes"
    PROCEDIMIENTOS = "procedimientos"
    MAOS = "maos"
    CERTIFICADOS = "certificados"
    # Nuevas auditorías específicas sin consulta a vector store
    FORMULARIOS_LEGALES = "formularios_legales"
    RUT_VALIDACION = "rut_validacion"
    DATOS_PACIENTE = "datos_paciente"
    CONSISTENCIA_DOCUMENTO = "consistencia_documento"
    PAGADOR_ADRES = "pagador_adres"

class SpecialAuditResult(BaseModel):
    """Resultado específico para auditorías con formato JSON predefinido"""
    identificacion_reclamacion: str = Field(description="Número de la reclamación (nombre del archivo PDF)")
    estado_glosa: int = Field(description="0 = sin glosa, 1 = con glosa")
    justificacion: str = Field(description="Justificación de la glosa o 'No aplica'")
    documentos_referenciados: str = Field(description="Documentos referenciados o 'No aplica'")
    clasificacion: Optional[str] = Field(default=None, description="Código de clasificación de la glosa")
    description: str = Field(description="Descripción de la glosa o 'No aplica'")

class IndividualAuditResult(BaseModel):
    """Resultado de una auditoría individual especializada"""
    audit_type: AuditType
    response: AuditResponse
    justification: str = Field(description="Explicación detallada de todos los hallazgos encontrados")
    glosas_detectadas: List[Dict] = Field(default_factory=list, description="Lista de glosas oficiales detectadas del documento predefinido")
    special_result: Optional[SpecialAuditResult] = Field(default=None, description="Resultado específico para auditorías con formato JSON predefinido")

class MasterAuditResult(BaseModel):
    """Resultado de la auditoría maestra consolidada"""
    decision: AuditDecision
    glosas: str = Field(description="Lista de glosas oficiales aplicadas con códigos y descripciones")
    justification: str = Field(description="Resumen general de la auditoría con hallazgos clave")

class FullAuditRequest(BaseModel):
    """Request para auditoría médica completa"""
    files_ids: List[int] = Field(default_factory=list, description="IDs de archivos para filtrar la búsqueda")
    k: int = Field(default=10, ge=1, le=50, description="Número de documentos a recuperar por búsqueda")
    max_context_chars: int = Field(default=5000, ge=1000, le=20000, description="Máximo de caracteres para contexto")
    temperature: float = Field(default=0.1, ge=0.0, le=1.0, description="Temperatura para generación de texto")
    max_tokens: int = Field(default=2000, ge=500, le=4000, description="Máximo de tokens para respuesta")
    top_p: float = Field(default=0.75, ge=0.0, le=1.0, description="Top-p sampling parameter")
    run_master_audit: bool = Field(default=True, description="Ejecutar auditoría maestra consolidada")
    custom_queries: Optional[Dict[str, str]] = Field(default=None, description="Consultas personalizadas para cada tipo de auditoría. Ej: {'factura': 'factura IPS número 123', 'medicamentos': 'paracetamol ibuprofeno'}")
    # Nuevo parámetro para elegir formato de respuesta
    response_format: str = Field(default="v2", description="Formato de respuesta: 'v1' (formato original) o 'v2' (nuevo formato JSON)")

class FullAuditResponse(BaseModel):
    """Response para auditoría médica completa (formato v1 - retrocompatibilidad)"""
    success: bool
    individual_audits: List[IndividualAuditResult]
    master_audit: Optional[MasterAuditResult] = None
    documents_retrieved: int
    model_used: str
    execution_time_seconds: float
    error: Optional[str] = None

class QuestionAuditRequest(BaseModel):
    """Request para auditoría basada en pregunta específica"""
    query: str = Field(description="Pregunta o consulta de auditoría específica")
    files_ids: List[int] = Field(default_factory=list, description="IDs de archivos para filtrar la búsqueda")
    k: int = Field(default=10, ge=1, le=50, description="Número de documentos a recuperar")
    max_context_chars: int = Field(default=5000, ge=1000, le=20000, description="Máximo de caracteres para contexto")
    temperature: float = Field(default=0.1, ge=0.0, le=1.0, description="Temperatura para generación de texto")
    max_tokens: int = Field(default=2000, ge=500, le=4000, description="Máximo de tokens para respuesta")
    top_p: float = Field(default=0.75, ge=0.0, le=1.0, description="Top-p sampling parameter")
    use_structured_output: bool = Field(default=True, description="Usar salida estructurada JSON")

class QuestionAuditResponse(BaseModel):
    """Response para auditoría basada en pregunta"""
    success: bool
    answer: Dict[str, Any]  # Puede ser dict estructurado o string simple
    context_used: str
    documents_retrieved: int
    query: str
    model_used: str
    context_length: int
    response_length: int
    execution_time_seconds: float
    error: Optional[str] = None

# Nuevos schemas para el formato JSON v2

class GlosaTotalClassification(BaseModel):
    """Clasificación de glosa total"""
    codigo: str = Field(description="Código de glosa")
    descripcion: str = Field(description="Descripción del tipo de glosa")
    justificacion: str = Field(description="Justificación específica por la que la reclamación se glosa totalmente")
    referencias: List[str] = Field(default_factory=list, description="Referencias a documentos usando formato documento/pagina")

class GlosaParcialClassification(BaseModel):
    """Clasificación de glosa parcial para un ítem específico"""
    codigo: int = Field(description="Código de la glosa parcial")
    descripcion: str = Field(description="Descripción de la glosa parcial")
    justificacion: str = Field(description="Justificación específica de la glosa parcial aplicada al ítem")
    referencias: List[str] = Field(default_factory=list, description="Referencias a documentos usando formato documento/pagina")

class ItemReclamado(BaseModel):
    """Ítem individual de la reclamación"""
    codigo: str = Field(description="Código alfanumérico del ítem reclamado")
    nombre: str = Field(description="Nombre del ítem reclamado")
    glosa_parcial: bool = Field(description="Indica si el ítem tiene glosa parcial")
    valor: Union[int, float] = Field(description="Valor del ítem")
    clasificacion_glosas: Optional[List[GlosaParcialClassification]] = Field(default=None, description="Clasificaciones aplicadas a la glosa parcial (solo si glosa_parcial=true)")
    
    def model_dump(self, **kwargs):
        """Personalizar serialización para omitir clasificacion_glosas si está vacío o glosa_parcial=false"""
        data = super().model_dump(**kwargs)
        # Si no hay glosa parcial, no incluir clasificacion_glosas
        if not self.glosa_parcial or not self.clasificacion_glosas:
            data.pop('clasificacion_glosas', None)
        return data

class AuditResponseV2(BaseModel):
    """Response principal para auditoría médica formato v2"""
    identificacion_reclamacion: str = Field(description="Identificador de la reclamación")
    glosa_total: bool = Field(description="Indica si hay alguna glosa total sobre la reclamación")
    justificacion: str = Field(description="Justificación general de la glosa total (si aplica)")
    clasificacion_glosas_totales: List[GlosaTotalClassification] = Field(default_factory=list, description="Solo glosas totales de la reclamación")
    items_reclamados: List[ItemReclamado] = Field(description="Lista de ítems de la reclamación")

class FullAuditResponseV2(BaseModel):
    """Response completa para auditoría médica formato v2"""
    success: bool
    audit_result: Optional[AuditResponseV2] = None
    documents_retrieved: int
    model_used: str
    execution_time_seconds: float
    error: Optional[str] = None
