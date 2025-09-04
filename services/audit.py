"""
Servicio de auditoría médica especializado para facturas de accidentes de tránsito (AT/ECAT) en Colombia.
Implementa 7 auditorías especializadas y una auditoría maestra consolidada.
"""
import logging
import time
import json
from typing import Dict, List, Optional, Union

from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain_core.caches import BaseCache
from langchain_core.callbacks.manager import Callbacks
from langchain_community.chat_models import ChatOCIGenAI

# Reconstruir el modelo Pydantic para evitar el error de clase no definida
ChatOCIGenAI.model_rebuild(_types_namespace={"BaseCache": BaseCache, "Callbacks": Callbacks})

from core.config import settings
from services.tools.oci_rag_tool import OCIRAGTool
from schemas.audit import (
    AuditResponse, AuditDecision, AuditType, 
    IndividualAuditResult, MasterAuditResult,
    FullAuditResponse, QuestionAuditResponse,
    # Nuevos schemas v2
    AuditResponseV2, FullAuditResponseV2, 
    GlosaTotalClassification, GlosaParcialClassification, ItemReclamado
)

logger = logging.getLogger(__name__)

class MedicalAuditService:
    """
    Servicio de auditoría médica especializado para cuentas médicas de accidentes de tránsito (AT/ECAT) en Colombia.
    Implementa 7 auditorías especializadas y una auditoría maestra consolidada.
    """

    def __init__(self):
        """Inicializar servicio de auditoría médica"""
        try:
            # Initialize the OCI Generative AI Chat Model
            self.llm = ChatOCIGenAI(
                model_id         = settings.CON_GEN_AI_CHAT_MODEL_ID,
                service_endpoint = settings.CON_GEN_AI_SERVICE_ENDPOINT,
                compartment_id   = settings.CON_COMPARTMENT_ID,
                provider         = settings.CON_GEN_AI_CHAT_MODEL_PROVIDER,
                is_stream        = False,
                auth_type        = "API_KEY",
                auth_profile     = settings.OCI_PROFILE,
                model_kwargs = {
                    "temperature": 0.1,
                    "max_tokens": 2000,
                    "frequency_penalty": 0.0,
                    "presence_penalty": 0.0,
                    "top_k": 0,
                    "top_p": 0.75,
                }
            )
            
            # Initialize RAG tool for vector search
            self.rag_tool = OCIRAGTool()
            
            # Initialize output parsers
            self.audit_output_parser = self._get_audit_output_parser()
            self.master_output_parser = self._get_master_output_parser()
            self.audit_v2_output_parser = self._get_audit_v2_output_parser()
            
            logger.info(f"[AUDIT] Servicio de auditoría médica inicializado con modelo: {settings.CON_GEN_AI_CHAT_MODEL_ID}")
            
        except Exception as e:
            logger.error(f"[AUDIT] Error inicializando servicio de auditoría: {str(e)}")
            raise

    def _get_audit_output_parser(self) -> StructuredOutputParser:
        """Inicializar parser de salida estructurada para auditorías individuales"""
        response_schemas = [
            ResponseSchema(
                name="response",
                description="La respuesta debe ser únicamente 'Cumple' o 'No cumple' basado en el análisis de la auditoría específica",
                type="string",
            ),
            ResponseSchema(
                name="justification",
                description="Explicación detallada de todos los hallazgos encontrados en la auditoría específica, evidencias específicas, discrepancias identificadas, y razones que sustentan la respuesta de cumplimiento",
                type="string",
            ),
        ]
        return StructuredOutputParser.from_response_schemas(response_schemas)

    def _get_master_output_parser(self) -> StructuredOutputParser:
        """Inicializar parser de salida estructurada para auditoría maestra"""
        response_schemas = [
            ResponseSchema(
                name="decision",
                description="Decisión final de la auditoría: 'Aprobada total', 'Aprobada parcial', 'Devuelta', o 'Anulada'",
                type="string",
            ),
            ResponseSchema(
                name="glosas",
                description="Lista de glosas oficiales aplicadas con códigos y descripciones",
                type="string",
            ),
            ResponseSchema(
                name="justification",
                description="Resumen general de la auditoría con hallazgos clave y razones de la decisión final",
                type="string",
            ),
        ]
        return StructuredOutputParser.from_response_schemas(response_schemas)

    def _get_audit_v2_output_parser(self) -> StructuredOutputParser:
        """Inicializar parser de salida estructurada para formato v2"""
        response_schemas = [
            ResponseSchema(
                name="identificacion_reclamacion",
                description="Identificador de la reclamación (nombre del archivo PDF principal)",
                type="string",
            ),
            ResponseSchema(
                name="glosa_total",
                description="Indica si hay alguna glosa total sobre la reclamación (true/false)",
                type="boolean",
            ),
            ResponseSchema(
                name="justificacion",
                description="Justificación general de la glosa total (si aplica) o descripción del estado de la reclamación",
                type="string",
            ),
            ResponseSchema(
                name="clasificacion_glosas_totales",
                description="Lista de glosas totales con formato: [{'codigo': 'XXX', 'descripcion': 'desc', 'justificacion': 'just', 'referencias': ['doc/pag']}]",
                type="array",
            ),
            ResponseSchema(
                name="items_reclamados", 
                description="Lista de ítems con formato: [{'codigo': 'XXX', 'nombre': 'nombre', 'glosa_parcial': true/false, 'valor': 0.0, 'clasificacion_glosas': []}]",
                type="array",
            ),
        ]
        return StructuredOutputParser.from_response_schemas(response_schemas)

    def _get_factura_prompt(self) -> str:
        """Prompt 1: Auditoría de factura de la IPS"""
        return """Eres un auditor médico especializado en facturación de accidentes de tránsito (AT/ECAT) en Colombia.

Tarea: Analiza la factura médica y verifica los siguientes campos obligatorios:

1. Número de factura: debe estar presente y ser alfanumérico.
2. Fecha de emisión: debe estar en formato dd/mm/aaaa.
3. Nombre y documento del paciente: debe coincidir con la historia clínica.
4. Valor total: debe ser un número válido en COP.
5. Detalle de cargos: debe incluir descripción, código, cantidad, valor unitario y total.
6. CUFE: debe estar presente y ser un código alfanumérico largo.

IMPORTANTE: Cuando hagas referencia a hallazgos específicos, usa el formato de página que aparece en el documento y extrae los datos específicos:
- Para referenciar página 10: página 10 o p10
- Para referenciar página 5: página 5 o p5
- Ejemplo: "Falta número de factura en página 3" o "Número de factura encontrado: 'FAC-2024-001' en p3"
- SIEMPRE extrae y muestra los datos específicos que encontraste, no solo menciones la página
- OBLIGATORIO: Para cada hallazgo, incluye el valor específico encontrado, por ejemplo:
  * "Número de factura: 'FAC-123456' en página 3"
  * "Valor total: '$4,246,800.00' en página 9"
  * "CUFE: 'CUFE-123456789-2024' en p3"
  * "Paciente: 'Juan Pérez, CC 12345678' en página 10"

Contexto:
{context}

Pregunta:
¿La factura cumple con todos los requisitos legales y técnicos?

Respuesta requerida:
{{
  "response": "Cumple" o "No cumple",
  "justification": "Lista de hallazgos específicos con referencias a páginas usando formato 'página X' o 'pX' y datos extraídos específicos para campos faltantes, errores de formato, inconsistencias o datos vacíos. OBLIGATORIO: Para cada hallazgo incluir el valor específico encontrado, por ejemplo: 'Número de factura: FAC-123456 en página 3', 'Valor total: $4,246,800.00 en p9'."
}}"""

    def _get_historia_clinica_prompt(self) -> str:
        """Prompt 2: Auditoría de historia clínica"""
        return """Eres un auditor médico especializado en historia clínica de accidentes de tránsito (AT/ECAT) en Colombia.

Tarea: Analiza la historia clínica y verifica los siguientes campos:

1. TRIAGE: debe estar presente y clasificado según protocolo.
2. Motivo de consulta: debe mencionar accidente, trauma o ECAT.
3. Diagnóstico principal y relacionados: deben ser compatibles con lo facturado.
4. Notas médicas y evolución: deben describir evolución del paciente.
5. Órdenes médicas: deben incluir medicamentos (CUM), exámenes (CUPS) y procedimientos.
6. Epicrisis: debe estar presente si hubo hospitalización o cirugía.

IMPORTANTE: Cuando hagas referencia a hallazgos específicos, usa el formato de página que aparece en el documento y extrae los datos específicos:
- Para referenciar página 10: página 10 o p10
- Para referenciar página 5: página 5 o p5
- Ejemplo: "TRIAGE no encontrado en página 2" o "TRIAGE encontrado: 'Nivel 3' en p2"
- SIEMPRE extrae y muestra los datos específicos que encontraste, no solo menciones la página
- OBLIGATORIO: Para cada hallazgo, incluye el valor específico encontrado, por ejemplo:
  * "TRIAGE: 'Nivel 2' en página 2"
  * "Motivo de consulta: 'Accidente de tránsito' en página 10"
  * "Diagnóstico: 'Fractura dental' en p10"
  * "Paciente: 'María García, CC 87654321' en página 10"

Contexto:
{context}

Pregunta:
¿La historia clínica cumple con los estándares de documentación médica?

Respuesta requerida:
{{
  "response": "Cumple" o "No cumple",
  "justification": "Lista de hallazgos específicos con referencias a páginas usando formato 'página X' o 'pX' y datos extraídos específicos para secciones faltantes, diagnósticos no compatibles, o evolución incompleta. OBLIGATORIO: Para cada hallazgo incluir el valor específico encontrado, por ejemplo: 'TRIAGE: Nivel 2 en página 2', 'Diagnóstico: Fractura dental en p10'."
}}"""

    def _get_medicamentos_prompt(self) -> str:
        """Prompt 3: Auditoría de órdenes y administración de medicamentos"""
        return """Eres un auditor médico especializado en control de medicamentos en accidentes de tránsito (AT/ECAT) en Colombia.

Tarea: Analiza las órdenes médicas y registros de administración:

1. Medicamento cobrado → debe estar en órdenes médicas.
2. Cada orden médica → debe tener firma/sello del médico.
3. Medicamento ordenado → debe tener registro de administración por enfermería.
4. Si falta medicamento en órdenes → glosa.
5. Si falta registro de administración → glosa.

IMPORTANTE: Cuando hagas referencia a hallazgos específicos, usa el formato de página que aparece en el documento y extrae los datos específicos:
- Para referenciar página 10: página 10 o p10
- Para referenciar página 5: página 5 o p5
- Ejemplo: "Medicamento X sin orden médica en página 4" o "Medicamento encontrado: 'Paracetamol 500mg' en p4"
- SIEMPRE extrae y muestra los datos específicos que encontraste, no solo menciones la página
- OBLIGATORIO: Para cada hallazgo, incluye el valor específico encontrado, por ejemplo:
  * "Medicamento: 'Paracetamol 500mg' en página 4"
  * "Dosis: '1 tableta cada 8 horas' en p4"
  * "CUM: 'CUM-123456' en página 4"
  * "Médico: 'Dr. Juan Pérez' en p4"

Contexto:
{context}

Pregunta:
¿Los medicamentos administrados están debidamente ordenados y registrados?

Respuesta requerida:
{{
  "response": "Cumple" o "No cumple",
  "justification": "Lista de medicamentos con inconsistencias, órdenes sin firma, o registros de administración faltantes usando formato 'página X' o 'pX' para referenciar páginas específicas. OBLIGATORIO: Para cada hallazgo incluir el valor específico encontrado, por ejemplo: 'Medicamento: Paracetamol 500mg en página 4', 'CUM: CUM-123456 en p4'."
}}"""

    def _get_examenes_prompt(self) -> str:
        """Prompt 4: Auditoría de exámenes de laboratorio e imágenes"""
        return """Eres un auditor médico especializado en exámenes diagnósticos en accidentes de tránsito (AT/ECAT) en Colombia.

Tarea: Analiza los exámenes médicos:

1. Examen cobrado → debe estar en órdenes médicas.
2. Examen realizado → debe tener informe escrito del especialista.
3. Si examen cobrado no tiene informe → glosa.
4. Si examen no está en órdenes → glosa.

IMPORTANTE: Cuando hagas referencia a hallazgos específicos, usa el formato de página que aparece en el documento y extrae los datos específicos:
- Para referenciar página 10: página 10 o p10
- Para referenciar página 5: página 5 o p5
- Ejemplo: "Radiografía sin informe en página 6" o "Radiografía encontrada: 'RX Torax PA' en p6"
- SIEMPRE extrae y muestra los datos específicos que encontraste, no solo menciones la página
- OBLIGATORIO: Para cada hallazgo, incluye el valor específico encontrado, por ejemplo:
  * "Examen: 'Radiografía Torax PA' en página 6"
  * "CUPS: 'CUPS-123456' en p6"
  * "Especialista: 'Dr. Ana López' en página 6"
  * "Fecha: '15/03/2024' en p6"

Contexto:
{context}

Pregunta:
¿Los exámenes realizados están debidamente ordenados e interpretados?

Respuesta requerida:
{{
  "response": "Cumple" o "No cumple",
  "justification": "Lista de exámenes con inconsistencias, informes faltantes o órdenes no encontradas usando formato 'página X' o 'pX' para referenciar páginas específicas. OBLIGATORIO: Para cada hallazgo incluir el valor específico encontrado, por ejemplo: 'Examen: Radiografía Torax PA en página 6', 'CUPS: CUPS-123456 en p6'."
}}"""

    def _get_procedimientos_prompt(self) -> str:
        """Prompt 5: Auditoría de procedimientos y cirugías"""
        return """Eres un auditor médico especializado en procedimientos quirúrgicos en accidentes de tránsito (AT/ECAT) en Colombia.

Tarea: Analiza los procedimientos médicos:

1. Procedimiento en factura → debe estar ordenado y realizado.
2. Nota operatoria: debe incluir técnica, complicaciones y materiales usados.
3. Cirujano, anestesiólogo y ayudante: deben estar mencionados y firmados.
4. Si falta nota operatoria → glosa.
5. Si no corresponde con diagnóstico → glosa.
6. Si se facturaron honorarios sin registro → glosa.

IMPORTANTE: Cuando hagas referencia a hallazgos específicos, usa el formato de página que aparece en el documento y extrae los datos específicos:
- Para referenciar página 10: página 10 o p10
- Para referenciar página 5: página 5 o p5
- Ejemplo: "Nota operatoria incompleta en página 8" o "Procedimiento encontrado: 'Apendicectomía' en p8"
- SIEMPRE extrae y muestra los datos específicos que encontraste, no solo menciones la página
- OBLIGATORIO: Para cada hallazgo, incluye el valor específico encontrado, por ejemplo:
  * "Procedimiento: 'Apendicectomía' en página 8"
  * "Cirujano: 'Dr. Carlos Ruiz' en p8"
  * "Fecha: '20/03/2024' en página 8"
  * "Técnica: 'Laparoscópica' en p8"

Contexto:
{context}

Pregunta:
¿Los procedimientos quirúrgicos están debidamente documentados y justificados?

Respuesta requerida:
{{
  "response": "Cumple" o "No cumple",
  "justification": "Lista de procedimientos con inconsistencias, notas operatorias incompletas o personal no registrado usando formato 'página X' o 'pX' para referenciar páginas específicas. OBLIGATORIO: Para cada hallazgo incluir el valor específico encontrado, por ejemplo: 'Procedimiento: Apendicectomía en página 8', 'Cirujano: Dr. Carlos Ruiz en p8'."
}}"""

    def _get_maos_prompt(self) -> str:
        """Prompt 6: Auditoría de materiales de osteosíntesis (MAOS)"""
        return """Eres un auditor médico especializado en materiales quirúrgicos en accidentes de tránsito (AT/ECAT) en Colombia.

Tarea: Analiza los materiales de osteosíntesis:

1. Factura del proveedor: debe estar presente y legible.
2. CUFE del proveedor: debe existir.
3. Comparación de valores: IPS vs proveedor (máximo 12% de incremento).
4. Si falta factura → glosa.
5. Si valores no coinciden → glosa.
6. Si cantidades/dispositivos no coinciden → glosa.

IMPORTANTE: Cuando hagas referencia a hallazgos específicos, usa el formato de página que aparece en el documento y extrae los datos específicos:
- Para referenciar página 10: página 10 o p10
- Para referenciar página 5: página 5 o p5
- Ejemplo: "Factura de proveedor faltante en página 12" o "Material encontrado: 'Placa de titanio 3.5mm' en p12"
- SIEMPRE extrae y muestra los datos específicos que encontraste, no solo menciones la página
- OBLIGATORIO: Para cada hallazgo, incluye el valor específico encontrado, por ejemplo:
  * "Material: 'Placa de titanio 3.5mm' en página 12"
  * "Cantidad: '2 unidades' en p12"
  * "Valor: '$150,000.00' en página 12"
  * "Proveedor: 'Proveedor XYZ' en p12"

Contexto:
{context}

Pregunta:
¿Los materiales quirúrgicos están debidamente facturados y justificados?

Respuesta requerida:
{{
  "response": "Cumple" o "No cumple",
  "justification": "Lista de materiales con inconsistencias, facturas faltantes o valores fuera de rango usando formato 'página X' o 'pX' para referenciar páginas específicas. OBLIGATORIO: Para cada hallazgo incluir el valor específico encontrado, por ejemplo: 'Material: Placa de titanio 3.5mm en página 12', 'Valor: $150,000.00 en p12'."
}}"""

    def _get_certificados_prompt(self) -> str:
        """Prompt 7: Auditoría de certificados adicionales"""
        return """Eres un auditor médico especializado en documentación legal en accidentes de tránsito (AT/ECAT) en Colombia.

Tarea: Analiza los certificados adicionales:

1. Certificado de autoridad (policía): debe estar presente y legible.
2. Certificado SOAT: debe estar presente y con datos consistentes.
3. Si falta o es ilegible → glosa.

IMPORTANTE: Cuando hagas referencia a hallazgos específicos, usa el formato de página que aparece en el documento y extrae los datos específicos:
- Para referenciar página 10: página 10 o p10
- Para referenciar página 5: página 5 o p5
- Ejemplo: "Certificado de policía faltante en página 15" o "Certificado encontrado: 'Póliza SOAT 123456' en p15"
- SIEMPRE extrae y muestra los datos específicos que encontraste, no solo menciones la página
- OBLIGATORIO: Para cada hallazgo, incluye el valor específico encontrado, por ejemplo:
  * "Póliza SOAT: 'SOAT-123456789' en página 15"
  * "Certificado policía: 'Cert-2024-001' en p15"
  * "Fecha accidente: '15/03/2024' en página 15"
  * "Autoridad: 'Policía Nacional' en p15"

Contexto:
{context}

Pregunta:
¿Los certificados legales están presentes y son válidos?

Respuesta requerida:
{{
  "response": "Cumple" o "No cumple",
  "justification": "Lista de certificados faltantes, ilegibles o con datos inconsistentes usando formato 'página X' o 'pX' para referenciar páginas específicas. OBLIGATORIO: Para cada hallazgo incluir el valor específico encontrado, por ejemplo: 'Póliza SOAT: SOAT-123456789 en página 15', 'Certificado policía: Cert-2024-001 en p15'."
}}"""

    def _get_formularios_legales_prompt(self) -> str:
        """Prompt 8: Validación de formularios requeridos por ley"""
        return """Eres un auditor médico especializado en validación de formularios legales para accidentes de tránsito (AT/ECAT) en Colombia.

Tarea: Analizar el contenido del archivo PDF para verificar si contiene al menos uno de los siguientes formularios oficiales:

Formularios requeridos:
1. Formulario Único de Reclamación de los Prestadores de Servicios de Salud (FURIPS)
2. Formulario Único de Reclamación de Gastos de Transporte y Movilización de Víctimas

Proceso de validación:
- Revisar página por página buscando el nombre completo de los formularios
- La detección debe ser exacta o muy cercana (tolerando errores menores de OCR)
- No aceptar coincidencias parciales irrelevantes
- Si se encuentra cualquiera de los formularios, la validación es exitosa

Contexto disponible: {context}

Responde en formato JSON:
{{
  "response": "Cumple" o "No cumple",
  "justification": "Si es válida: 'Se encontró el formulario: [nombre del formulario] en la página [número]'. Si no es válida: 'No se encontró el Formulario Único de Reclamación de los Prestadores de Servicios de Salud ni el Formulario Único de Reclamación de Gastos de Transporte y Movilización de Víctimas'",
  "special_result": {{
    "identificacion_reclamacion": "[nombre del archivo PDF]",
    "estado_glosa": 0 o 1,
    "justificacion": "No aplica" o "Se glosa la reclamación por accidente de tránsito debido a la ausencia del Formulario Único de Reclamación de los Prestadores de Servicios de Salud (FURIPS) y del Formulario Único de Reclamación de Gastos de Transporte y Movilización de Víctimas, documentos obligatorios según la normatividad vigente para el cobro ante la ADRES.",
    "documentos_referenciados": "No aplica" o "Formulario Único de Reclamación de los Prestadores de Servicios de Salud ni el Formulario Único de Reclamación de Gastos de Transporte y Movilización de Víctimas",
    "clasificacion": null o "332",
    "description": "No aplica" o "Ausencia, enmendaduras, incompletitud o ilegibilidad en el soporte del detalle de cargos, incluyendo la omisión de documentos obligatorios exigidos por la normatividad para el tipo de reclamación."
  }}
}}"""

    def _get_rut_validacion_prompt(self) -> str:
        """Prompt 9: Validación de RUT en existencia y vigencia"""
        return """Eres un auditor médico especializado en validación de documentos tributarios para accidentes de tránsito (AT/ECAT) en Colombia.

Tarea: Verificar si el documento PDF contiene una copia del RUT (Registro Único Tributario) expedido por la DIAN, con fecha de expedición no mayor a 3 meses antes de la fecha de presentación.

Búsqueda del RUT:
- Buscar texto "Registro Único Tributario" o "RUT" en el documento
- Verificar formato oficial de la DIAN (no resúmenes ni transcripciones)

Campos obligatorios a validar:
- Número de NIT (con dígito de verificación)
- Nombre o Razón Social
- Tipo de documento
- Dirección
- Municipio
- Departamento
- Actividad Económica Principal
- Fecha de expedición (emitida por la DIAN)
- Código de verificación o QR de autenticidad

Validación de fecha:
- Comparar fecha de expedición del RUT con fecha de la factura (del XML IssueDate)
- Verificar que no han pasado más de 3 meses

Contexto disponible: {context}

Responde en formato JSON:
{{
  "response": "Cumple" o "No cumple",
  "justification": "Si es válido: 'Se encontró RUT y la fecha de expedición está dentro del rango permitido de 3 meses'. Si no es válido: 'No se encontró el documento RUT' o 'La fecha de expedición supera los 3 meses'",
  "special_result": {{
    "identificacion_reclamacion": "[nombre del archivo PDF]",
    "estado_glosa": 0 o 1,
    "justificacion": "No aplica" o "Se devuelve la reclamación por accidente de tránsito debido a la ausencia del Registro Único Tributario (RUT) o porque el documento no cumple con la vigencia mínima de tres (3) meses exigida por la normatividad vigente para radicación ante la ADRES.",
    "documentos_referenciados": "No aplica" o "RUT",
    "clasificacion": null o "816",
    "description": "No aplica" o "Falta de soporte obligatorio para la radicación."
  }}
}}"""

    def _get_datos_paciente_prompt(self) -> str:
        """Prompt 10: Validación de coincidencia de datos del paciente"""
        return """Eres un auditor médico especializado en validación de datos de pacientes para accidentes de tránsito (AT/ECAT) en Colombia.

Tarea: Verificar que los datos del paciente en el documento PDF coincidan exactamente con los datos del paciente facturado en el XML.

Campos a comparar:
- Tipo de documento (CC, TI, CE, Pasaporte, etc.)
- Número de documento (debe ser exacto)
- Nombre completo (permitir diferencias de mayúsculas/minúsculas y tildes)
- Fecha de nacimiento (si está presente)

Tolerancias permitidas:
- Diferencias de mayúsculas/minúsculas
- Presencia/ausencia de tildes
- Nombres compuestos y abreviaturas equivalentes
- Espacios adicionales o saltos de línea

Validación estricta:
- Número de documento debe coincidir exactamente
- No aceptar coincidencias parciales

Contexto disponible: {context}

Responde en formato JSON:
{{
  "response": "Cumple" o "No cumple",
  "justification": "Si es válido: 'Datos coincidentes. La información del paciente en el documento PDF y la factura XML corresponde a la misma persona'. Si no es válido: 'Datos no coincidentes. Diferencias detectadas en: [lista de campos]'",
  "special_result": {{
    "identificacion_reclamacion": "[nombre del archivo PDF]",
    "estado_glosa": 0 o 1,
    "justificacion": "No aplica" o "Se devuelve la reclamación por accidente de tránsito debido a que fue presentada fuera del plazo máximo de un (1) año contado a partir de la fecha del accidente o de la prestación del servicio, incumpliendo lo establecido en el Decreto 780 de 2016 y demás normatividad vigente.",
    "documentos_referenciados": "No aplica" o "Factura / Historia Clinica",
    "clasificacion": null o "814",
    "description": "No aplica" o "Presentación de la factura o reclamación por fuera del término establecido por la ley para su radicación."
  }}
}}"""

    def _get_consistencia_documento_prompt(self) -> str:
        """Prompt 11: Validación de consistencia de número de documento"""
        return """Eres un auditor médico especializado en validación de consistencia documental para accidentes de tránsito (AT/ECAT) en Colombia.

Tarea: Verificar que el número de documento del paciente sea exactamente el mismo en todos los documentos PDF relacionados al caso.

Proceso de validación:
- Extraer tipo y número de documento de cada PDF
- Comparar que todos tengan el mismo número exacto
- Verificar consistencia del tipo de documento

Tolerancias permitidas:
- Diferencias de formato (puntos, guiones): 1.234.567 vs 1234567
- Mayúsculas/minúsculas en tipo de documento

Validación estricta:
- Número debe coincidir exactamente en todos los documentos
- No se aceptan diferencias en dígitos, letras o caracteres
- Tipo de documento debe ser consistente

Contexto disponible: {context}

Responde en formato JSON:
{{
  "response": "Cumple" o "No cumple",
  "justification": "Si es válido: 'Consistencia verificada. El número de documento del paciente ([TIPO] [NÚMERO]) es el mismo en todos los documentos'. Si no es válido: 'Inconsistencias detectadas en el número de documento. Documento(s) con valor diferente: [detalles]'",
  "special_result": {{
    "identificacion_reclamacion": "[nombre del archivo PDF]",
    "estado_glosa": 0 o 1,
    "justificacion": "No aplica" o "Se glosa la reclamación por accidente de tránsito debido a que el número de documento del usuario no coincide entre los diferentes soportes presentados (FURIPS, factura, historia clínica y formato de transporte), lo que impide validar que todos correspondan a la misma persona.",
    "documentos_referenciados": "No aplica" o "Historia Clinica",
    "clasificacion": null o "326",
    "description": "No aplica" o "Inconsistencia en la identificación del usuario."
  }}
}}"""

    def _get_pagador_adres_prompt(self) -> str:
        """Prompt 12: Validación de NIT y Nombre del Pagador (ADRES)"""
        return """Eres un auditor médico especializado en validación de pagadores para accidentes de tránsito (AT/ECAT) en Colombia.

Tarea: Verificar que el NIT y nombre del pagador en la factura correspondan a la ADRES.

Datos oficiales esperados:
- Nombre: "Administradora de los Recursos del Sistema General de Seguridad Social en Salud – ADRES" 
  (se acepta abreviatura "ADRES" y variaciones menores por OCR)
- NIT: 901.037.916-1 (con o sin puntos y guión opcional)

Tolerancias permitidas:
- NIT con o sin puntos y con o sin guión
- Nombre con abreviatura "ADRES" oficial
- Diferencias menores de acentos o mayúsculas por OCR

Validación estricta:
- NIT debe coincidir exactamente con el oficial
- Nombre debe corresponder a la denominación oficial de ADRES
- No aceptar coincidencias parciales con otras entidades

Contexto disponible: {context}

Responde en formato JSON:
{{
  "response": "Cumple" o "No cumple",
  "justification": "Si es válido: 'El pagador de la factura corresponde a la ADRES. NIT: 901.037.916-1, Nombre: [ENCONTRADO]'. Si no es válido: 'El pagador no corresponde a la ADRES. Datos encontrados: NIT: [ENCONTRADO], Nombre: [ENCONTRADO]'",
  "special_result": {{
    "identificacion_reclamacion": "[nombre del archivo PDF]",
    "estado_glosa": 0 o 1,
    "justificacion": "No aplica" o "Se devuelve la reclamación por accidente de tránsito debido a que en los documentos presentados (factura, FURIPS) el NIT y/o nombre del pagador no corresponde a la ADRES, por lo que la entidad no es competente para el pago según la normatividad vigente.",
    "documentos_referenciados": "No aplica" o "Factura / FURIPS",
    "clasificacion": null o "815",
    "description": "No aplica" o "La factura o reclamación se presenta a una entidad diferente a la responsable del pago."
  }}
}}"""

    def _get_master_prompt(self) -> str:
        """Prompt maestro: Orquestador de auditoría final"""
        return """Eres un auditor médico especializado en cuentas médicas de accidentes de tránsito (AT/ECAT) en Colombia.

Tarea: Consolida los resultados de las 12 sub‑auditorías y emite una decisión final.

Sub‑auditorías realizadas:
1. Factura de la IPS: {resultado_factura}
2. Historia clínica: {resultado_historia}
3. Órdenes y medicamentos: {resultado_medicamentos}
4. Exámenes diagnósticos: {resultado_examenes}
5. Procedimientos quirúrgicos: {resultado_procedimientos}
6. Materiales quirúrgicos (MAOS): {resultado_maos}
7. Certificados legales: {resultado_certificados}
8. Formularios legales: {resultado_formularios}
9. RUT validación: {resultado_rut}
10. Datos del paciente: {resultado_datos}
11. Consistencia de documento: {resultado_consistencia}
12. Pagador ADRES: {resultado_pagador}

Tarea final:
1. Si todos los resultados son "Cumple" → clasificar como "Aprobada total".
2. Si hay uno o más "No cumple" → clasificar como "Aprobada parcial" o "Devuelta" según gravedad.
3. Asignar glosas oficiales del Manual ADRES a cada incumplimiento.
4. Generar un JSON con:
   - Decisión final ("Aprobada total", "Aprobada parcial", "Devuelta", "Anulada")
   - Lista de glosas aplicadas con códigos oficiales
   - Justificación general del veredicto

Respuesta requerida:
{{
  "decision": "Aprobada total" o "Aprobada parcial" o "Devuelta" o "Anulada",
  "glosas": "Lista de glosas oficiales aplicadas con códigos y descripciones",
  "justification": "Resumen general de la auditoría con hallazgos clave"
}}"""

    def _extract_relevant_glosas(self, audit_type: str) -> List[Dict]:
        """
        Extraer glosas relevantes del documento de glosas predefinido según el tipo de auditoría. 
        NO INVENTA GLOSAS - las extrae del documento oficial usando AUDIT_GLOSAS_FILE_ID.
        """
        try:
            logger.info(f"[AUDIT] Extrayendo glosas relevantes para tipo: {audit_type} desde file_id: {settings.AUDIT_GLOSAS_FILE_ID}")
            
            # Buscar el documento de glosas oficial con consulta más específica
            search_query = f"Tipo: {audit_type} glosa detalle segmento"
            
            glosas_context = self.rag_tool.oci_vector_search_context_only(
                input=search_query,
                files_ids=[settings.AUDIT_GLOSAS_FILE_ID],  # Documento con las glosas predefinidas
                k=50  # Más glosas para asegurar cobertura completa
            )
            
            if not glosas_context or not glosas_context.get("documents"):
                logger.warning(f"[AUDIT] No se encontró contexto de glosas para {audit_type}")
                return []
            
            # Construir el texto completo de las glosas desde los documentos
            glosas_text_parts = []
            logger.info(f"[AUDIT] Procesando {len(glosas_context['documents'])} documentos recuperados:")
            
            for i, doc in enumerate(glosas_context["documents"]):
                file_id = doc.get("file_id")
                chunk_id = doc.get("chunk_id")
                content = doc.get("content", "")
                
                logger.info(f"[AUDIT]   Doc {i+1}: file_id={file_id}, chunk_id={chunk_id}, caracteres={len(content)}")
                
                if file_id == settings.AUDIT_GLOSAS_FILE_ID:  # Verificar que sea del archivo correcto
                    glosas_text_parts.append(content)
                    # Log del contenido del chunk para debugging
                    logger.info(f"[AUDIT]     Contenido chunk {chunk_id}: {content[:300]}...")
                else:
                    logger.warning(f"[AUDIT]     Doc {i+1} no pertenece al file_id {settings.AUDIT_GLOSAS_FILE_ID}, ignorando")
            
            glosas_text = "\n\n".join(glosas_text_parts)
            
            if not glosas_text.strip():
                logger.warning(f"[AUDIT] No se encontró contenido de glosas para {audit_type}")
                return []
            
            logger.info(f"[AUDIT] Contexto de glosas obtenido: {len(glosas_text)} caracteres total")
            logger.info(f"[AUDIT] Contexto completo para {audit_type}:")
            logger.info(f"[AUDIT] {'-'*80}")
            logger.info(f"[AUDIT] {glosas_text}")
            logger.info(f"[AUDIT] {'-'*80}")
            
            # Procesar el texto para extraer glosas manualmente
            glosas_extraidas = []
            
            # Dividir el texto en secciones por "### Glosa:"
            secciones = glosas_text.split("### Glosa:")
            
            for seccion in secciones[1:]:  # Saltar la primera sección vacía
                try:
                    lines = seccion.strip().split('\n')
                    if not lines:
                        continue
                    
                    # Extraer código de glosa (primera línea)
                    codigo_line = lines[0].strip()
                    codigo = codigo_line.split()[0] if codigo_line else ""
                    
                    # Buscar información específica
                    tipo = ""
                    segmento = ""
                    detalle = ""
                    glosa_a_reclamacion = ""
                    contexto = ""
                    observaciones = ""
                    
                    for line in lines:
                        line = line.strip()
                        if line.startswith("- **Tipo:**"):
                            tipo = line.replace("- **Tipo:**", "").strip()
                        elif line.startswith("- **SEGMENTO:**"):
                            segmento = line.replace("- **SEGMENTO:**", "").strip()
                        elif line.startswith("- **Detalle de glosa:**"):
                            detalle = line.replace("- **Detalle de glosa:**", "").strip()
                        elif line.startswith("- **Glosa a reclamacion:**"):
                            glosa_a_reclamacion = line.replace("- **Glosa a reclamacion:**", "").strip()
                        elif line.startswith("- **Glosa a ITEM:**"):
                            glosa_a_reclamacion = line.replace("- **Glosa a ITEM:**", "").strip()
                        elif line.startswith("- **Contexto:**"):
                            contexto = line.replace("- **Contexto:**", "").strip()
                        elif line.startswith("- **Observacion:**"):
                            observaciones = line.replace("- **Observacion:**", "").strip()
                    
                    # Solo incluir si el tipo coincide exactamente
                    if tipo.lower() == audit_type.lower() and codigo and detalle:
                        glosa = {
                            "codigo": codigo,
                            "tipo": tipo,
                            "segmento": segmento,
                            "detalle": detalle,
                            "glosa_a_reclamacion": glosa_a_reclamacion,
                            "contexto": contexto,
                            "observaciones": observaciones
                        }
                        glosas_extraidas.append(glosa)
                        
                except Exception as e:
                    logger.warning(f"[AUDIT] Error procesando sección de glosa: {str(e)}")
                    continue
            
            logger.info(f"[AUDIT] Glosas extraídas para {audit_type}: {len(glosas_extraidas)} glosas oficiales")
            
            # Log de las primeras glosas para debugging
            for i, glosa in enumerate(glosas_extraidas[:3]):
                logger.info(f"[AUDIT] Glosa {i+1}: {glosa['codigo']} - {glosa['detalle'][:50]}...")
            
            return glosas_extraidas
                
        except Exception as e:
            logger.error(f"[AUDIT] Error extrayendo glosas para {audit_type}: {str(e)}")
            return []

    def _run_special_audit(self, prompt_template: str, audit_name: str, 
                          files_ids: List[int], search_query: str = None, 
                          k: int = 10, max_context_chars: int = 5000) -> Dict:
        """
        Ejecutar una auditoría especial que NO requiere extracción de glosas del vector store.
        Estas auditorías tienen las glosas predefinidas en el prompt.
        """
        try:
            logger.info(f"[AUDIT] Ejecutando auditoría especial: {audit_name}")
            
            # Obtener contexto usando búsqueda vectorial normal (para el contenido de los documentos)
            if not search_query:
                # Consultas predefinidas para auditorías especiales
                search_queries = {
                    "Formularios Legales": "formulario único reclamación prestadores servicios salud FURIPS transporte movilización víctimas",
                    "RUT Validación": "registro único tributario RUT DIAN fecha expedición NIT",
                    "Datos Paciente": "paciente identificación nombre documento número fecha nacimiento",
                    "Consistencia Documento": "número documento identificación paciente CC TI CE pasaporte",
                    "Pagador ADRES": "pagador NIT ADRES administradora recursos sistema seguridad social"
                }
                search_query = search_queries.get(audit_name, f"{audit_name.lower()} auditoría")
            
            # Búsqueda vectorial para obtener el contexto de los documentos
            context_result = self.rag_tool.oci_vector_search_context_only(
                input=search_query,
                files_ids=files_ids,
                k=k
            )
            
            if not context_result or not context_result.get("documents"):
                logger.warning(f"[AUDIT] No se encontró contexto para {audit_name}")
                context = "No se encontró información relevante en los documentos proporcionados."
            else:
                context = context_result.get("context", "")
            
            # Truncar contexto si excede el límite
            if len(context) > max_context_chars:
                context = context[:max_context_chars] + "...[contexto truncado]"
            
            logger.info(f"[AUDIT] Contexto recuperado para {audit_name}: {len(context)} caracteres de {context_result.get('total_documents', 0)} documentos")
            
            # NO EXTRAER GLOSAS del vector store - estas auditorías tienen glosas predefinidas
            logger.info(f"[AUDIT] Auditoría especial {audit_name}: usando glosas predefinidas en el prompt")
            
            # Create prompt template
            prompt = PromptTemplate(
                template=prompt_template,
                input_variables=["context"]
            )
            
            # Create the chain (sin parser estructurado por defecto)
            chain = prompt | self.llm
            response = chain.invoke({"context": context})
            
            # Intentar parsear como JSON usando el parser estructurado
            try:
                parsed_result = self.audit_output_parser.parse(response.content)
                processed_result = {
                    "response": str(parsed_result.get("response", "No cumple")),
                    "justification": str(parsed_result.get("justification", "Error en el análisis")),
                    "special_result": parsed_result.get("special_result", None)
                }
            except Exception as parse_error:
                logger.warning(f"[AUDIT] Error parseando respuesta JSON para {audit_name}: {str(parse_error)}")
                
                # Fallback: extraer respuesta manualmente del texto
                response_text = response.content.strip()
                
                # Buscar patrones de "Cumple" o "No cumple" en el texto
                if "No cumple" in response_text:
                    response_value = "No cumple"
                elif "Cumple" in response_text:
                    response_value = "Cumple"
                else:
                    response_value = "No cumple"
                
                # Intentar extraer special_result básico del texto si hay error
                special_result = {
                    "identificacion_reclamacion": "archivo_no_identificado",
                    "estado_glosa": 1,  # Asumir que hay glosa si hay error
                    "justificacion": "Error en el procesamiento de la auditoría especial",
                    "documentos_referenciados": "No determinado",
                    "clasificacion": "999",
                    "description": "Error en el análisis automatizado"
                }
                
                processed_result = {
                    "response": response_value,
                    "justification": response_text[:1000] + "..." if len(response_text) > 1000 else response_text,
                    "special_result": special_result
                }
            
            # Las auditorías especiales NO tienen glosas_detectadas del vector store
            processed_result["glosas_detectadas"] = []
            
            logger.info(f"[AUDIT] Auditoría especial {audit_name} completada: {processed_result['response']}")
            return processed_result
            
        except Exception as e:
            logger.error(f"[AUDIT] Error en auditoría especial {audit_name}: {str(e)}")
            return {
                "response": "No cumple",
                "justification": f"Error en auditoría especial {audit_name}: {str(e)}",
                "glosas_detectadas": [],
                "special_result": {
                    "identificacion_reclamacion": "error_procesamiento",
                    "estado_glosa": 1,
                    "justificacion": f"Error técnico en auditoría: {str(e)}",
                    "documentos_referenciados": "Sistema",
                    "clasificacion": "999",
                    "description": "Error técnico en el procesamiento"
                }
            }

    def _run_specialized_audit(self, prompt_template: str, audit_name: str, 
                             files_ids: List[int], search_query: str = None, k: int = 10, 
                             max_context_chars: int = 5000) -> Dict:
        """Ejecutar una auditoría especializada usando un prompt específico"""
        try:
            logger.info(f"[AUDIT] Ejecutando auditoría especializada: {audit_name}")
            
            # Si no se proporciona search_query, usar consultas predefinidas
            if not search_query:
                search_queries = {
                    "Factura": "factura médica número fecha emisión CUFE valor total detalle cargos",
                    "Historia Clínica": "historia clínica triage motivo consulta diagnóstico notas médicas órdenes epicrisis",
                    "Medicamentos": "órdenes médicas medicamentos administración enfermería firma médico CUM",
                    "Exámenes": "exámenes laboratorio imágenes diagnósticas CUPS informe especialista",
                    "Procedimientos": "procedimientos quirúrgicos nota operatoria cirujano anestesiólogo",
                    "MAOS": "materiales osteosíntesis factura proveedor CUFE proveedor incremento 12%",
                    "Certificados": "certificado autoridad policía SOAT ECAT documentación legal"
                }
                search_query = search_queries.get(audit_name, f"auditoría {audit_name.lower()}")
            
            logger.info(f"[AUDIT] Búsqueda RAG para {audit_name}: '{search_query}' en archivos {files_ids}")
            
            # Get specialized context for this audit using RAG tool
            context_result = self.rag_tool.oci_vector_search_context_only(search_query, files_ids, k)
            
            if context_result["total_documents"] == 0:
                logger.warning(f"[AUDIT] No se encontró contexto relevante para auditoría {audit_name}")
                return {
                    "response": "No cumple",
                    "justification": f"No se encontró información relevante para la auditoría de {audit_name}. Consulta: '{search_query}'"
                }
            
            # Build context string from documents
            context_parts = []
            for doc in context_result["documents"]:
                context_parts.append(f"Documento {doc['index']}:\n{doc['content']}")
            
            context = "\n\n".join(context_parts)
            
            # Limit context to max_context_chars
            if len(context) > max_context_chars:
                context = context[:max_context_chars] + "...[contexto truncado]"
            
            logger.info(f"[AUDIT] Contexto recuperado para {audit_name}: {len(context)} caracteres de {context_result['total_documents']} documentos")
            
            # EXTRAER GLOSAS RELEVANTES DEL DOCUMENTO PREDEFINIDO
            relevant_glosas = self._extract_relevant_glosas(audit_name)
            logger.info(f"[AUDIT] Glosas extraídas para {audit_name}: {len(relevant_glosas)} glosas oficiales (file_id: {settings.AUDIT_GLOSAS_FILE_ID})")
            
            # Create prompt template
            prompt = PromptTemplate(
                template=prompt_template,
                input_variables=["context"]
            )
            
            # Create the chain (sin parser para manejar errores mejor)
            chain = prompt | self.llm
            
            # Run the chain
            response = chain.invoke({"context": context})
            
            # Intentar parsear la respuesta con manejo de errores mejorado
            try:
                # Primero intentar con el parser estructurado
                parsed_result = self.audit_output_parser.parse(response.content)
                processed_result = {
                    "response": str(parsed_result.get("response", "No cumple")),
                    "justification": str(parsed_result.get("justification", "Error en el análisis"))
                }
            except Exception as parse_error:
                logger.warning(f"[AUDIT] Error parseando respuesta para {audit_name}: {str(parse_error)}")
                
                # Fallback: extraer respuesta manualmente del texto
                response_text = response.content.strip()
                
                # Buscar patrones de "Cumple" o "No cumple" en el texto
                if "No cumple" in response_text:
                    response_value = "No cumple"
                elif "Cumple" in response_text:
                    response_value = "Cumple"
                else:
                    response_value = "No cumple"
                
                # Usar el texto completo como justificación
                processed_result = {
                    "response": response_value,
                    "justification": response_text[:1000] + "..." if len(response_text) > 1000 else response_text
                }
            
            # AGREGAR LAS GLOSAS EXTRAÍDAS AL RESULTADO
            processed_result["glosas_detectadas"] = relevant_glosas
            
            logger.info(f"[AUDIT] Auditoría {audit_name} completada: {processed_result['response']} con {len(relevant_glosas)} glosas oficiales")
            return processed_result
            
        except Exception as e:
            logger.error(f"[AUDIT] Error en auditoría {audit_name}: {str(e)}")
            return {
                "response": "No cumple",
                "justification": f"Error en auditoría de {audit_name}: {str(e)}"
            }

    def run_full_medical_audit(self, files_ids: List[int] = None, k: int = 10,
                             max_context_chars: int = 5000, temperature: float = 0.1,
                             max_tokens: int = 2000, top_p: float = 0.75,
                             run_master_audit: bool = True, custom_queries: Dict[str, str] = None,
                             response_format: str = "v1", identificacion_reclamacion: str = None) -> Union[FullAuditResponse, FullAuditResponseV2]:
        """
        Ejecutar auditoría médica completa con 12 auditorías especializadas
        
        Args:
            files_ids: Lista de IDs de archivos para filtrar la búsqueda
            k: Número de documentos a recuperar por búsqueda
            max_context_chars: Máximo de caracteres para contexto
            temperature: Temperatura para generación de texto
            max_tokens: Máximo de tokens para respuesta
            top_p: Top-p sampling parameter
            run_master_audit: Ejecutar auditoría maestra consolidada
            response_format: Formato de respuesta 'v1' (original) o 'v2' (nuevo JSON)
            
        Returns:
            FullAuditResponse (v1) o FullAuditResponseV2 (v2) con resultados de todas las auditorías
        """
        start_time = time.time()
        
        try:
            logger.info(f"[AUDIT] Iniciando auditoría médica completa")
            
            if files_ids is None:
                files_ids = []
                
            # Update LLM parameters
            self.llm.model_kwargs.update({
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p,
            })

            # Run 7 specialized audits
            logger.info("[AUDIT] Ejecutando 7 auditorías especializadas...")
            
            individual_audits = []
            
            # 1. Factura audit
            factura_query = custom_queries.get("factura") if custom_queries else None
            factura_result = self._run_specialized_audit(
                self._get_factura_prompt(), "Factura", files_ids, factura_query, k, max_context_chars
            )
            individual_audits.append(IndividualAuditResult(
                audit_type=AuditType.FACTURA,
                response=AuditResponse(factura_result["response"]),
                justification=factura_result["justification"],
                glosas_detectadas=factura_result.get("glosas_detectadas", [])
            ))
            
            # 2. Historia clínica audit
            historia_query = custom_queries.get("historia_clinica") if custom_queries else None
            historia_result = self._run_specialized_audit(
                self._get_historia_clinica_prompt(), "Historia Clínica", files_ids, historia_query, k, max_context_chars
            )
            individual_audits.append(IndividualAuditResult(
                audit_type=AuditType.HISTORIA_CLINICA,
                response=AuditResponse(historia_result["response"]),
                justification=historia_result["justification"],
                glosas_detectadas=historia_result.get("glosas_detectadas", [])
            ))
            
            # 3. Medicamentos audit
            medicamentos_query = custom_queries.get("medicamentos") if custom_queries else None
            medicamentos_result = self._run_specialized_audit(
                self._get_medicamentos_prompt(), "Medicamentos", files_ids, medicamentos_query, k, max_context_chars
            )
            individual_audits.append(IndividualAuditResult(
                audit_type=AuditType.MEDICAMENTOS,
                response=AuditResponse(medicamentos_result["response"]),
                justification=medicamentos_result["justification"],
                glosas_detectadas=medicamentos_result.get("glosas_detectadas", [])
            ))
            
            # 4. Exámenes audit
            examenes_query = custom_queries.get("examenes") if custom_queries else None
            examenes_result = self._run_specialized_audit(
                self._get_examenes_prompt(), "Exámenes", files_ids, examenes_query, k, max_context_chars
            )
            individual_audits.append(IndividualAuditResult(
                audit_type=AuditType.EXAMENES,
                response=AuditResponse(examenes_result["response"]),
                justification=examenes_result["justification"],
                glosas_detectadas=examenes_result.get("glosas_detectadas", [])
            ))
            
            # 5. Procedimientos audit
            procedimientos_query = custom_queries.get("procedimientos") if custom_queries else None
            procedimientos_result = self._run_specialized_audit(
                self._get_procedimientos_prompt(), "Procedimientos", files_ids, procedimientos_query, k, max_context_chars
            )
            individual_audits.append(IndividualAuditResult(
                audit_type=AuditType.PROCEDIMIENTOS,
                response=AuditResponse(procedimientos_result["response"]),
                justification=procedimientos_result["justification"],
                glosas_detectadas=procedimientos_result.get("glosas_detectadas", [])
            ))
            
            # 6. MAOS audit
            maos_query = custom_queries.get("maos") if custom_queries else None
            maos_result = self._run_specialized_audit(
                self._get_maos_prompt(), "MAOS", files_ids, maos_query, k, max_context_chars
            )
            individual_audits.append(IndividualAuditResult(
                audit_type=AuditType.MAOS,
                response=AuditResponse(maos_result["response"]),
                justification=maos_result["justification"],
                glosas_detectadas=maos_result.get("glosas_detectadas", [])
            ))
            
            # 7. Certificados audit
            certificados_query = custom_queries.get("certificados") if custom_queries else None
            certificados_result = self._run_specialized_audit(
                self._get_certificados_prompt(), "Certificados", files_ids, certificados_query, k, max_context_chars
            )
            individual_audits.append(IndividualAuditResult(
                audit_type=AuditType.CERTIFICADOS,
                response=AuditResponse(certificados_result["response"]),
                justification=certificados_result["justification"],
                glosas_detectadas=certificados_result.get("glosas_detectadas", [])
            ))

            # 8. Formularios Legales audit (especial - sin glosas del vector store)
            formularios_query = custom_queries.get("formularios_legales") if custom_queries else None
            formularios_result = self._run_special_audit(
                self._get_formularios_legales_prompt(), "Formularios Legales", files_ids, formularios_query, k, max_context_chars
            )
            individual_audits.append(IndividualAuditResult(
                audit_type=AuditType.FORMULARIOS_LEGALES,
                response=AuditResponse(formularios_result["response"]),
                justification=formularios_result["justification"],
                glosas_detectadas=formularios_result.get("glosas_detectadas", []),
                special_result=formularios_result.get("special_result")
            ))
            
            # 9. RUT Validación audit (especial - sin glosas del vector store)
            rut_query = custom_queries.get("rut_validacion") if custom_queries else None
            rut_result = self._run_special_audit(
                self._get_rut_validacion_prompt(), "RUT Validación", files_ids, rut_query, k, max_context_chars
            )
            individual_audits.append(IndividualAuditResult(
                audit_type=AuditType.RUT_VALIDACION,
                response=AuditResponse(rut_result["response"]),
                justification=rut_result["justification"],
                glosas_detectadas=rut_result.get("glosas_detectadas", []),
                special_result=rut_result.get("special_result")
            ))
            
            # 10. Datos Paciente audit (especial - sin glosas del vector store)
            datos_query = custom_queries.get("datos_paciente") if custom_queries else None
            datos_result = self._run_special_audit(
                self._get_datos_paciente_prompt(), "Datos Paciente", files_ids, datos_query, k, max_context_chars
            )
            individual_audits.append(IndividualAuditResult(
                audit_type=AuditType.DATOS_PACIENTE,
                response=AuditResponse(datos_result["response"]),
                justification=datos_result["justification"],
                glosas_detectadas=datos_result.get("glosas_detectadas", []),
                special_result=datos_result.get("special_result")
            ))
            
            # 11. Consistencia Documento audit (especial - sin glosas del vector store)
            consistencia_query = custom_queries.get("consistencia_documento") if custom_queries else None
            consistencia_result = self._run_special_audit(
                self._get_consistencia_documento_prompt(), "Consistencia Documento", files_ids, consistencia_query, k, max_context_chars
            )
            individual_audits.append(IndividualAuditResult(
                audit_type=AuditType.CONSISTENCIA_DOCUMENTO,
                response=AuditResponse(consistencia_result["response"]),
                justification=consistencia_result["justification"],
                glosas_detectadas=consistencia_result.get("glosas_detectadas", []),
                special_result=consistencia_result.get("special_result")
            ))
            
            # 12. Pagador ADRES audit (especial - sin glosas del vector store)
            pagador_query = custom_queries.get("pagador_adres") if custom_queries else None
            pagador_result = self._run_special_audit(
                self._get_pagador_adres_prompt(), "Pagador ADRES", files_ids, pagador_query, k, max_context_chars
            )
            individual_audits.append(IndividualAuditResult(
                audit_type=AuditType.PAGADOR_ADRES,
                response=AuditResponse(pagador_result["response"]),
                justification=pagador_result["justification"],
                glosas_detectadas=pagador_result.get("glosas_detectadas", []),
                special_result=pagador_result.get("special_result")
            ))

            master_audit = None
            if run_master_audit:
                logger.info("[AUDIT] Ejecutando auditoría maestra consolidada...")
                master_audit = self._run_master_audit(individual_audits)

            execution_time = time.time() - start_time
            
            # Get documents retrieved count (estimate from last search)
            documents_retrieved = sum([
                len(self.rag_tool.oci_vector_search_context_only("auditoría médica", files_ids, k)["documents"])
                for _ in range(12)  # Approximate count for all 12 audits (7 traditional + 5 special)
            ])

            logger.info(f"[AUDIT] Auditoría médica completa finalizada en {execution_time:.2f} segundos")
            logger.info(f"[AUDIT] Total auditorías ejecutadas: {len(individual_audits)} (7 tradicionales + 5 especiales)")

            # Retornar formato según solicitud
            if response_format == "v2":
                return self._generate_v2_response(
                    individual_audits, master_audit, documents_retrieved, execution_time, identificacion_reclamacion
                )
            else:
                return FullAuditResponse(
                    success=True,
                    individual_audits=individual_audits,
                    master_audit=master_audit,
                    documents_retrieved=documents_retrieved,
                    model_used=settings.CON_GEN_AI_CHAT_MODEL_ID,
                    execution_time_seconds=execution_time
                )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[AUDIT] Error en auditoría médica completa: {str(e)}")
            
            if response_format == "v2":
                return FullAuditResponseV2(
                    success=False,
                    audit_result=None,
                    documents_retrieved=0,
                    model_used=settings.CON_GEN_AI_CHAT_MODEL_ID,
                    execution_time_seconds=execution_time,
                    error=str(e)
                )
            else:
                return FullAuditResponse(
                    success=False,
                    individual_audits=[],
                    master_audit=None,
                    documents_retrieved=0,
                    model_used=settings.CON_GEN_AI_CHAT_MODEL_ID,
                    execution_time_seconds=execution_time,
                    error=str(e)
                )

    def _run_master_audit(self, individual_audits: List[IndividualAuditResult]) -> MasterAuditResult:
        """Ejecutar auditoría maestra consolidada usando glosas reales extraídas del documento oficial"""
        try:
            logger.info("[AUDIT] Ejecutando auditoría maestra consolidada")
            
            # CONSOLIDAR TODAS LAS GLOSAS REALES DE LAS AUDITORÍAS INDIVIDUALES
            all_glosas = []
            audit_summary = []
            
            for audit in individual_audits:
                audit_name = audit.audit_type.value
                audit_summary.append(f"{audit_name}: {audit.response.value}")
                
                # Agregar glosas detectadas de esta auditoría
                if audit.glosas_detectadas:
                    for glosa in audit.glosas_detectadas:
                        glosa_with_source = glosa.copy()
                        glosa_with_source["audit_source"] = audit_name
                        all_glosas.append(glosa_with_source)
                    
                    logger.info(f"[AUDIT] {audit_name}: {len(audit.glosas_detectadas)} glosas oficiales detectadas")
                else:
                    logger.info(f"[AUDIT] {audit_name}: Sin glosas detectadas")
            
            logger.info(f"[AUDIT] Total glosas consolidadas: {len(all_glosas)} glosas oficiales")
            
            # Determinar decisión basada en los resultados
            no_cumple_count = sum(1 for audit in individual_audits if audit.response == AuditResponse.NO_CUMPLE)
            
            if no_cumple_count == 0:
                decision = AuditDecision.APROBADA_TOTAL
            elif no_cumple_count >= 5:  # Mayoría no cumple
                decision = AuditDecision.DEVUELTA
            elif len(all_glosas) > 10:  # Muchas glosas detectadas
                decision = AuditDecision.DEVUELTA
            else:
                decision = AuditDecision.APROBADA_PARCIAL
            
            # Construir lista de glosas oficiales con formato estándar
            glosas_text_parts = []
            for i, glosa in enumerate(all_glosas[:20], 1):  # Limitar a 20 glosas principales
                codigo = glosa.get("codigo", f"GL{i:03d}")
                detalle = glosa.get("detalle", "Glosa sin detalle")
                audit_source = glosa.get("audit_source", "General")
                
                glosa_formatted = f"Código: {codigo} | Tipo: {glosa.get('tipo', audit_source)} | Segmento: {glosa.get('segmento', 'General')} | Detalle: {detalle[:100]}..."
                glosas_text_parts.append(glosa_formatted)
            
            glosas_text = "\n".join(glosas_text_parts) if glosas_text_parts else "No se detectaron glosas específicas"
            
            # Justificación basada en auditorías individuales
            justification_parts = [
                f"La cuenta médica fue clasificada como {decision.value} basándose en los siguientes hallazgos:",
                "",
                "Resumen de auditorías:"
            ]
            justification_parts.extend(audit_summary)
            
            if all_glosas:
                justification_parts.extend([
                    "",
                    f"Se detectaron {len(all_glosas)} glosas oficiales del documento file_id {settings.AUDIT_GLOSAS_FILE_ID}:",
                    f"- Glosas de Factura: {len([g for g in all_glosas if g.get('audit_source') == 'factura'])}",
                    f"- Glosas de Medicamentos: {len([g for g in all_glosas if g.get('audit_source') == 'medicamentos'])}",
                    f"- Glosas de Exámenes: {len([g for g in all_glosas if g.get('audit_source') == 'examenes'])}",
                    f"- Glosas de Procedimientos: {len([g for g in all_glosas if g.get('audit_source') == 'procedimientos'])}",
                    f"- Otras glosas: {len([g for g in all_glosas if g.get('audit_source') not in ['factura', 'medicamentos', 'examenes', 'procedimientos']])}"
                ])
            
            justification = "\n".join(justification_parts)
            
            master_result = MasterAuditResult(
                decision=decision,
                glosas=glosas_text,
                justification=justification
            )
            
            logger.info(f"[AUDIT] Auditoría maestra completada: {master_result.decision.value} con {len(all_glosas)} glosas oficiales")
            return master_result
            
        except Exception as e:
            logger.error(f"[AUDIT] Error en auditoría maestra: {str(e)}")
            return MasterAuditResult(
                decision=AuditDecision.DEVUELTA,
                glosas="Error en procesamiento de auditoría maestra",
                justification=f"Error en auditoría maestra: {str(e)}"
            )

    def answer_audit_question(self, query: str, files_ids: List[int] = None, 
                            k: int = 10, max_context_chars: int = 5000,
                            temperature: float = 0.1, max_tokens: int = 2000,
                            top_p: float = 0.75, use_structured_output: bool = True) -> QuestionAuditResponse:
        """
        Responder una pregunta específica de auditoría usando RAG
        
        Args:
            query: Pregunta o consulta de auditoría específica
            files_ids: Lista de IDs de archivos para filtrar la búsqueda
            k: Número de documentos a recuperar
            max_context_chars: Máximo de caracteres para contexto
            temperature: Temperatura para generación de texto
            max_tokens: Máximo de tokens para respuesta
            top_p: Top-p sampling parameter
            use_structured_output: Usar salida estructurada JSON
            
        Returns:
            QuestionAuditResponse con la respuesta a la pregunta
        """
        start_time = time.time()
        
        try:
            logger.info(f"[AUDIT] Respondiendo pregunta de auditoría: {query[:100]}...")
            
            if files_ids is None:
                files_ids = []
                
            # Update LLM parameters
            self.llm.model_kwargs.update({
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p,
            })
            
            # Get relevant context from vector search
            context_result = self.rag_tool.oci_vector_search_context_only(query, files_ids, k)
            
            if context_result["total_documents"] == 0:
                execution_time = time.time() - start_time
                return QuestionAuditResponse(
                    success=True,
                    answer={"response": "No cumple", "justification": "No se encontró información relevante en los documentos para responder tu pregunta."},
                    context_used="",
                    documents_retrieved=0,
                    query=query,
                    model_used=settings.CON_GEN_AI_CHAT_MODEL_ID,
                    context_length=0,
                    response_length=0,
                    execution_time_seconds=execution_time
                )
            
            # Build context string from documents
            context_parts = []
            for doc in context_result["documents"]:
                context_parts.append(f"Documento {doc['index']}:\n{doc['content']}")
            
            context = "\n\n".join(context_parts)
            
            # Limit context to max_context_chars
            if len(context) > max_context_chars:
                context = context[:max_context_chars] + "...[contexto truncado]"

            if use_structured_output:
                # Use structured output with JSON format
                logger.info("[AUDIT] Generando respuesta estructurada")
                
                system_prompt = """Eres un auditor médico especializado en cuentas médicas de accidentes de tránsito (AT/ECAT) en Colombia. 

Tu rol es analizar documentos médicos relacionados con accidentes de tránsito, incluyendo:
- Facturas médicas
- Historia clínica
- Órdenes médicas
- Epicrisis
- Imágenes diagnósticas
- Facturas de proveedores
- Certificados médicos

OBJETIVOS DE LA AUDITORÍA:
1. **Verificar la legitimidad** de los servicios médicos prestados
2. **Validar la facturación** contra las regulaciones colombianas y SOAT
3. **Identificar discrepancias** entre servicios facturados y documentación médica
4. **Detectar posibles fraudes** o sobrefacturación
5. **Evaluar la calidad** de la documentación médica
6. **Verificar el cumplimiento** de protocolos médicos estándar

DIRECTRICES IMPORTANTES:
- Analiza ÚNICAMENTE la información proporcionada en el contexto
- Sé preciso y objetivo en tus hallazgos
- Identifica claramente cualquier información faltante o inconsistente
- Evalúa la coherencia entre diferentes documentos médicos
- Considera las regulaciones colombianas de facturación médica y SOAT
- NO hagas referencia a documentos específicos - analiza la información de manera general

FORMATO DE RESPUESTA:
- **RESPUESTA**: Debe ser únicamente "Cumple" o "No cumple" basado en tu análisis
- **JUSTIFICACIÓN**: Debe incluir todos los hallazgos específicos, evidencias documentales, discrepancias encontradas, y razones detalladas que sustentan tu decisión de cumplimiento

Recuerda: Tu análisis debe ser profesional, objetivo y basado únicamente en la evidencia documental proporcionada."""
                
                prompt_template = PromptTemplate(
                    template="""
{system_prompt}

Basándote en los siguientes documentos médicos, responde a esta pregunta: {query}

DOCUMENTOS MÉDICOS:
{context}

TAREA:
Realiza una auditoría médica completa de los documentos proporcionados siguiendo las directrices establecidas.

IMPORTANTE: 
- Tu respuesta debe ser binaria: "Cumple" o "No cumple"
- NO hagas referencia a documentos específicos - analiza la información de manera general
- Si los documentos cumplen con todas las regulaciones y estándares médicos: responde "Cumple"
- Si hay cualquier incumplimiento, discrepancia, o problema: responde "No cumple"

{format_instructions}

Responde ÚNICAMENTE usando el formato JSON esperado con "Cumple" o "No cumple" como respuesta.""",
                    input_variables=["query", "context"],
                    partial_variables={
                        "system_prompt": system_prompt,
                        "format_instructions": self.audit_output_parser.get_format_instructions()
                    }
                )
                
                # Create the chain
                chain = prompt_template | self.llm | self.audit_output_parser
                
                # Run the chain
                structured_result = chain.invoke({"query": query, "context": context})
                
                # Convert list results to strings if necessary
                def ensure_string(value):
                    if isinstance(value, list):
                        return "\n".join(str(item) for item in value)
                    return str(value)
                
                # Ensure all values are strings
                if isinstance(structured_result, dict):
                    answer = {
                        "response": ensure_string(structured_result.get("response", "")),
                        "justification": ensure_string(structured_result.get("justification", ""))
                    }
                else:
                    answer = ensure_string(structured_result)
            
            else:
                # Use free text response
                logger.info("[AUDIT] Generando respuesta de texto libre")
                
                system_prompt = """Eres un auditor médico especializado en cuentas médicas de accidentes de tránsito (AT/ECAT) en Colombia. 

Tu rol es analizar documentos médicos relacionados con accidentes de tránsito, incluyendo:
- Facturas médicas
- Historia clínica
- Órdenes médicas
- Epicrisis
- Imágenes diagnósticas
- Facturas de proveedores
- Certificados médicos

OBJETIVOS DE LA AUDITORÍA:
1. **Verificar la legitimidad** de los servicios médicos prestados
2. **Validar la facturación** contra las regulaciones colombianas y SOAT
3. **Identificar discrepancias** entre servicios facturados y documentación médica
4. **Detectar posibles fraudes** o sobrefacturación
5. **Evaluar la calidad** de la documentación médica
6. **Verificar el cumplimiento** de protocolos médicos estándar

DIRECTRICES IMPORTANTES:
- Analiza ÚNICAMENTE la información proporcionada en el contexto
- Sé preciso y objetivo en tus hallazgos
- Identifica claramente cualquier información faltante o inconsistente
- Evalúa la coherencia entre diferentes documentos médicos
- Considera las regulaciones colombianas de facturación médica y SOAT
- NO hagas referencia a documentos específicos - analiza la información de manera general

Recuerda: Tu análisis debe ser profesional, objetivo y basado únicamente en la evidencia documental proporcionada."""
                
                # Create chat prompt template
                prompt = ChatPromptTemplate.from_messages([
                    ("system", system_prompt),
                    ("human", """Basándote en los siguientes documentos médicos, responde a esta pregunta: {query}

DOCUMENTOS MÉDICOS:
{context}

Por favor proporciona una respuesta estructurada con:
1. **RESPUESTA**: Debe ser únicamente "Cumple" o "No cumple" basado en tu análisis de auditoría médica
2. **JUSTIFICACIÓN**: Explicación detallada de todos los hallazgos encontrados, evidencias específicas, discrepancias identificadas, y razones que sustentan tu decisión de cumplimiento

IMPORTANTE: 
- Tu respuesta debe ser binaria: "Cumple" o "No cumple"
- NO hagas referencia a documentos específicos - analiza la información de manera general
- Si los documentos cumplen con todas las regulaciones y estándares médicos: responde "Cumple"
- Si hay cualquier incumplimiento, discrepancia, o problema: responde "No cumple"

Analiza la información proporcionada de manera general sin citar documentos específicos.""")
                ])
                
                # Create the chain
                chain = prompt | self.llm | StrOutputParser()
                
                # Run the chain
                response = chain.invoke({"query": query, "context": context})
                answer = response.strip()

            execution_time = time.time() - start_time

            return QuestionAuditResponse(
                success=True,
                answer=answer,
                context_used=context,
                documents_retrieved=context_result["total_documents"],
                query=query,
                model_used=settings.CON_GEN_AI_CHAT_MODEL_ID,
                context_length=len(context),
                response_length=len(str(answer)),
                execution_time_seconds=execution_time
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[AUDIT] Error respondiendo pregunta de auditoría: {str(e)}")
            return QuestionAuditResponse(
                success=False,
                answer={},
                context_used="",
                documents_retrieved=0,
                query=query,
                model_used=settings.CON_GEN_AI_CHAT_MODEL_ID,
                context_length=0,
                response_length=0,
                execution_time_seconds=execution_time,
                error=str(e)
            )

    def run_full_medical_audit_v2(self, files_ids: List[int] = None, k: int = 30,
                                max_context_chars: int = 8000, temperature: float = 0.1,
                                max_tokens: int = 4000, top_p: float = 0.75, 
                                identificacion_reclamacion: str = None) -> FullAuditResponseV2:
        """
        Ejecutar auditoría médica completa con respuesta directa en formato v2
        Este método optimiza la auditoría para generar directamente el formato JSON v2
        """
        start_time = time.time()
        
        try:
            logger.info("[AUDIT] Iniciando auditoría médica completa v2 con formato JSON directo")
            
            if files_ids is None:
                files_ids = []
                
            # Update LLM parameters for comprehensive analysis
            self.llm.model_kwargs.update({
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p,
            })

            # Realizar búsqueda comprehensiva para obtener todo el contexto relevante
            comprehensive_query = "factura médica historia clínica órdenes medicamentos exámenes procedimientos MAOS certificados formularios RUT ADRES pagador FURIPS SOAT"
            
            context_result = self.rag_tool.oci_vector_search_context_only(
                comprehensive_query, files_ids, k
            )
            
            if context_result["total_documents"] == 0:
                return FullAuditResponseV2(
                    success=False,
                    audit_result=None,
                    documents_retrieved=0,
                    model_used=settings.CON_GEN_AI_CHAT_MODEL_ID,
                    execution_time_seconds=time.time() - start_time,
                    error="No se encontraron documentos para analizar"
                )
            
            # Build comprehensive context
            context_parts = []
            for doc in context_result["documents"]:
                context_parts.append(f"Documento {doc['index']}:\n{doc['content']}")
            
            context = "\n\n".join(context_parts)
            
            # Limit context
            if len(context) > max_context_chars:
                context = context[:max_context_chars] + "...[contexto truncado]"
            
            logger.info(f"[AUDIT] Contexto obtenido: {len(context)} caracteres de {context_result['total_documents']} documentos")
            
            # Create comprehensive audit prompt for v2 format
            v2_prompt = self._get_comprehensive_v2_prompt()
            
            prompt_template = PromptTemplate(
                template=v2_prompt,
                input_variables=["context"],
                partial_variables={
                    "format_instructions": self.audit_v2_output_parser.get_format_instructions()
                }
            )
            
            # Create chain with v2 parser
            chain = prompt_template | self.llm | self.audit_v2_output_parser
            
            # Execute comprehensive audit
            logger.info("[AUDIT] Ejecutando auditoría comprehensiva con formato v2")
            result = chain.invoke({"context": context})
            
            # Process and validate result
            audit_result = self._process_v2_result(result, identificacion_reclamacion)
            
            execution_time = time.time() - start_time
            
            logger.info(f"[AUDIT] Auditoría v2 completada en {execution_time:.2f} segundos")
            
            return FullAuditResponseV2(
                success=True,
                audit_result=audit_result,
                documents_retrieved=context_result["total_documents"],
                model_used=settings.CON_GEN_AI_CHAT_MODEL_ID,
                execution_time_seconds=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[AUDIT] Error en auditoría médica completa v2: {str(e)}")
            return FullAuditResponseV2(
                success=False,
                audit_result=None,
                documents_retrieved=0,
                model_used=settings.CON_GEN_AI_CHAT_MODEL_ID,
                execution_time_seconds=execution_time,
                error=str(e)
            )

    def _get_comprehensive_v2_prompt(self) -> str:
        """Prompt comprehensivo para auditoría v2 que genera directamente el formato JSON"""
        return """Eres un auditor médico especializado en cuentas médicas de accidentes de tránsito (AT/ECAT) en Colombia.

TAREA: Analiza los documentos médicos proporcionados y genera una respuesta de auditoría en formato JSON específico.

DOCUMENTOS A ANALIZAR:
{context}

PROCESO DE AUDITORÍA:
Revisa exhaustivamente los documentos para:

1. **GLOSAS TOTALES** (que anulan toda la reclamación):
   - Ausencia de formularios obligatorios (FURIPS)
   - RUT vencido o ausente  
   - Datos del paciente inconsistentes
   - Pagador incorrecto (debe ser ADRES)
   - Certificados legales faltantes
   - Factura duplicada
   - Prestación sin cobertura

2. **GLOSAS PARCIALES** (por ítems específicos):
   - Medicamentos sin orden médica (código 326)
   - Exámenes sin informe (código 332)
   - Procedimientos sin nota operatoria (código 101)
   - Facturación sin soporte (código 816)
   - MAOS sin justificación (código 299)

3. **ÍTEMS FACTURADOS**:
   - Extrae TODOS los servicios, medicamentos, exámenes, procedimientos de la factura
   - Asigna códigos únicos (ITM-001, ITM-002, etc.)
   - Valores exactos en números enteros
   - Solo incluye "clasificacion_glosas" si glosa_parcial=true

REGLAS IMPORTANTES:
- identificacion_reclamacion: Usar nombre del archivo principal (ej: "REC-2025-00123")
- glosa_total: true solo si hay glosas que anulan TODA la reclamación
- Códigos de glosas totales: String (ej: "GT001", "GT002") 
- Códigos de glosas parciales: Números enteros (ej: 101, 326, 332)
- Valores: números enteros sin decimales
- Referencias: formato "archivo.pdf/pagina" o "archivo.xml"
- Items sin glosas: NO incluir campo "clasificacion_glosas"

EJEMPLO DE FORMATO ESPERADO:
{{
  "identificacion_reclamacion": "REC-2025-00123",
  "glosa_total": true,
  "justificacion": "La reclamación se glosa en su totalidad debido a...",
  "clasificacion_glosas_totales": [
    {{
      "codigo": "GT001",
      "descripcion": "Factura duplicada",
      "justificacion": "Se encontró que la factura ya había sido presentada...",
      "referencias": ["FAC123456.pdf/3"]
    }}
  ],
  "items_reclamados": [
    {{
      "codigo": "ITM-001",
      "nombre": "Consulta médica general",
      "glosa_parcial": false,
      "valor": 50000
    }},
    {{
      "codigo": "ITM-002", 
      "nombre": "Radiografía odontológica",
      "glosa_parcial": true,
      "valor": 80000,
      "clasificacion_glosas": [
        {{
          "codigo": 101,
          "descripcion": "Falta de soporte clínico",
          "justificacion": "No se adjuntó la historia clínica...",
          "referencias": ["HISTORIA_CLINICA_2025.pdf/12"]
        }}
      ]
    }}
  ]
}}

{format_instructions}

IMPORTANTE: Responde ÚNICAMENTE con el JSON en el formato especificado, sin texto adicional."""

    def _process_v2_result(self, result: Dict, identificacion_reclamacion: str = None) -> AuditResponseV2:
        """Procesar y validar el resultado v2"""
        try:
            # Ensure required fields - usar el parámetro pasado o el del resultado
            identificacion_final = identificacion_reclamacion or result.get("identificacion_reclamacion", "reclamacion_auditoria")
            glosa_total = bool(result.get("glosa_total", False))
            justificacion = result.get("justificacion", "Auditoría procesada")
            
            # Process glosas totales
            glosas_totales = []
            for glosa_data in result.get("clasificacion_glosas_totales", []):
                if isinstance(glosa_data, dict):
                    glosa = GlosaTotalClassification(
                        codigo=str(glosa_data.get("codigo", "999")),
                        descripcion=glosa_data.get("descripcion", "Glosa sin descripción"),
                        justificacion=glosa_data.get("justificacion", "Sin justificación"),
                        referencias=glosa_data.get("referencias", [])
                    )
                    glosas_totales.append(glosa)
            
            # Process items reclamados
            items_reclamados = []
            for item_data in result.get("items_reclamados", []):
                if isinstance(item_data, dict):
                    # Process glosas parciales for this item
                    clasificacion_glosas = []
                    for glosa_parcial in item_data.get("clasificacion_glosas", []):
                        if isinstance(glosa_parcial, dict):
                            glosa = GlosaParcialClassification(
                                codigo=int(glosa_parcial.get("codigo", 999)),
                                descripcion=glosa_parcial.get("descripcion", "Glosa sin descripción"),
                                justificacion=glosa_parcial.get("justificacion", "Sin justificación"),
                                referencias=glosa_parcial.get("referencias", [])
                            )
                            clasificacion_glosas.append(glosa)
                    
                    # Solo incluir clasificacion_glosas si hay glosa parcial y hay glosas
                    kwargs = {
                        "codigo": item_data.get("codigo", "ITM_001"),
                        "nombre": item_data.get("nombre", "Servicio médico"),
                        "glosa_parcial": bool(item_data.get("glosa_parcial", False)),
                        "valor": int(float(item_data.get("valor", 0)))  # Convertir a entero
                    }
                    
                    # Solo agregar clasificacion_glosas si glosa_parcial=true y hay glosas
                    if kwargs["glosa_parcial"] and clasificacion_glosas:
                        kwargs["clasificacion_glosas"] = clasificacion_glosas
                    
                    item = ItemReclamado(**kwargs)
                    items_reclamados.append(item)
            
            # Ensure at least one item exists
            if not items_reclamados:
                items_reclamados.append(ItemReclamado(
                    codigo="ITM-001",
                    nombre="Servicios médicos generales",
                    glosa_parcial=False,
                    valor=0
                    # No incluir clasificacion_glosas para items sin glosa
                ))
            
            return AuditResponseV2(
                identificacion_reclamacion=identificacion_final,
                glosa_total=glosa_total,
                justificacion=justificacion,
                clasificacion_glosas_totales=glosas_totales,
                items_reclamados=items_reclamados
            )
            
        except Exception as e:
            logger.error(f"[AUDIT] Error procesando resultado v2: {str(e)}")
            # Return basic fallback response
            identificacion_fallback = identificacion_reclamacion or "error_procesamiento"
            return AuditResponseV2(
                identificacion_reclamacion=identificacion_fallback,
                glosa_total=True,
                justificacion=f"Error en el procesamiento de la auditoría: {str(e)}",
                clasificacion_glosas_totales=[GlosaTotalClassification(
                    codigo="999",
                    descripcion="Error de procesamiento",
                    justificacion=f"Error técnico: {str(e)}",
                    referencias=[]
                )],
                items_reclamados=[ItemReclamado(
                    codigo="ERROR_001",
                    nombre="Error en procesamiento",
                    glosa_parcial=False,
                    valor=0
                    # No incluir clasificacion_glosas para items sin glosa
                )]
            )

    def _generate_v2_response(self, individual_audits: List[IndividualAuditResult], 
                             master_audit: Optional[MasterAuditResult], 
                             documents_retrieved: int, execution_time: float,
                             identificacion_reclamacion: str = None) -> FullAuditResponseV2:
        """
        Generar respuesta en formato v2 basado en los resultados de auditorías individuales
        """
        try:
            logger.info("[AUDIT] Generando respuesta en formato v2")
            
            # Usar identificación proporcionada o valor por defecto
            identificacion_final = identificacion_reclamacion or "reclamacion_auditoria_medica"
            
            # Determinar si hay glosas totales
            glosas_totales = []
            glosa_total = False
            
            # Procesar auditorías especiales que pueden generar glosas totales
            special_audits = [audit for audit in individual_audits if audit.special_result is not None]
            
            for audit in special_audits:
                if audit.special_result and audit.special_result.estado_glosa == 1:
                    glosa_total = True
                    glosa = GlosaTotalClassification(
                        codigo=audit.special_result.clasificacion or "999",
                        descripcion=audit.special_result.description,
                        justificacion=audit.special_result.justificacion,
                        referencias=audit.special_result.documentos_referenciados.split(", ") if audit.special_result.documentos_referenciados != "No aplica" else []
                    )
                    glosas_totales.append(glosa)
            
            # Extraer items reclamados de la información disponible
            items_reclamados = []
            
            # Para cada auditoría que tenga glosas parciales, crear items
            for audit in individual_audits:
                if audit.glosas_detectadas and not audit.special_result:  # Solo auditorías tradicionales
                    for glosa in audit.glosas_detectadas:
                        # Crear item con glosa parcial
                        item = ItemReclamado(
                            codigo=f"{audit.audit_type.value.upper()}_001",
                            nombre=f"Servicio de {audit.audit_type.value}",
                            glosa_parcial=True,
                            valor=0.0,  # Valor por defecto, debería extraerse de la factura
                            clasificacion_glosas=[
                                GlosaParcialClassification(
                                    codigo=int(glosa.get("codigo", "999")),
                                    descripcion=glosa.get("detalle", "Glosa sin descripción"),
                                    justificacion=audit.justification[:200] + "..." if len(audit.justification) > 200 else audit.justification,
                                    referencias=[]  # Se pueden agregar referencias específicas
                                )
                            ]
                        )
                        items_reclamados.append(item)
            
            # Si no hay items con glosas parciales, crear al menos un item base
            if not items_reclamados:
                items_reclamados.append(ItemReclamado(
                    codigo="SERVICIO_001",
                    nombre="Servicios médicos generales",
                    glosa_parcial=False,
                    valor=0.0,
                    clasificacion_glosas=[]
                ))
            
            # Justificación general
            if glosa_total:
                justificacion = "La reclamación presenta glosas totales que impiden su aprobación."
            else:
                justificacion = "La reclamación ha sido procesada sin glosas totales."
            
            # Crear respuesta v2
            audit_result = AuditResponseV2(
                identificacion_reclamacion=identificacion_final,
                glosa_total=glosa_total,
                justificacion=justificacion,
                clasificacion_glosas_totales=glosas_totales,
                items_reclamados=items_reclamados
            )
            
            return FullAuditResponseV2(
                success=True,
                audit_result=audit_result,
                documents_retrieved=documents_retrieved,
                model_used=settings.CON_GEN_AI_CHAT_MODEL_ID,
                execution_time_seconds=execution_time
            )
            
        except Exception as e:
            logger.error(f"[AUDIT] Error generando respuesta v2: {str(e)}")
            return FullAuditResponseV2(
                success=False,
                audit_result=None,
                documents_retrieved=documents_retrieved,
                model_used=settings.CON_GEN_AI_CHAT_MODEL_ID,
                execution_time_seconds=execution_time,
                error=str(e)
            )
