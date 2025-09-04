# Ejemplos de Uso del Servicio de Auditoría Médica

El servicio de auditoría médica implementa 7 auditorías especializadas para cuentas médicas de accidentes de tránsito (AT/ECAT) en Colombia, siguiendo las regulaciones ADRES y SOAT.

## Endpoints Disponibles

### 1. Auditoría Médica Completa

**POST** `/audit/full-audit`

Ejecuta las 7 auditorías especializadas:
1. **Factura IPS**: Verifica campos obligatorios (número, fecha, CUFE, valor total)
2. **Historia Clínica**: Analiza TRIAGE, diagnósticos, evolución médica
3. **Medicamentos**: Valida órdenes médicas y administración
4. **Exámenes**: Verifica laboratorios e imágenes diagnósticas
5. **Procedimientos**: Analiza cirugías y notas operatorias
6. **MAOS**: Audita materiales de osteosíntesis
7. **Certificados**: Verifica documentación legal (SOAT, policía)

#### Ejemplo de Request:

```json
{
  "files_ids": [123, 456, 789],
  "k": 15,
  "max_context_chars": 8000,
  "temperature": 0.1,
  "max_tokens": 2500,
  "top_p": 0.75,
  "run_master_audit": true
}
```

#### Ejemplo de Response:

```json
{
  "success": true,
  "individual_audits": [
    {
      "audit_type": "factura",
      "response": "No cumple",
      "justification": "Número de factura: 'FAC-2024-001' en página 3, Valor total: '$4,246,800.00' en página 9, CUFE faltante en toda la documentación"
    },
    {
      "audit_type": "historia_clinica",
      "response": "Cumple",
      "justification": "TRIAGE: 'Nivel 2' en página 2, Motivo de consulta: 'Accidente de tránsito' en página 10, Diagnóstico: 'Fractura dental' en p10"
    }
  ],
  "master_audit": {
    "decision": "Devuelta",
    "glosas": "GLOSA-001: Factura sin CUFE válido, GLOSA-015: Documentación incompleta",
    "justification": "La cuenta presenta incumplimientos críticos en facturación que impiden su aprobación"
  },
  "documents_retrieved": 45,
  "model_used": "cohere.command-r-plus",
  "execution_time_seconds": 23.5
}
```

### 2. Auditoría por Pregunta Específica

**POST** `/audit/question`

Responde preguntas específicas de auditoría usando RAG.

#### Ejemplo de Request:

```json
{
  "query": "¿La factura cumple con todos los requisitos legales de facturación médica para accidentes de tránsito?",
  "files_ids": [123, 456],
  "k": 10,
  "max_context_chars": 5000,
  "temperature": 0.1,
  "max_tokens": 2000,
  "top_p": 0.75,
  "use_structured_output": true
}
```

#### Ejemplo de Response:

```json
{
  "success": true,
  "answer": {
    "response": "No cumple",
    "justification": "La factura presenta las siguientes deficiencias: 1) Falta el código CUFE requerido por la DIAN, 2) El valor total no coincide con la suma de los ítems detallados, 3) Ausencia de firma digital del prestador"
  },
  "context_used": "Documento 1: Factura médica número FAC-2024-001...",
  "documents_retrieved": 8,
  "query": "¿La factura cumple con todos los requisitos legales...",
  "model_used": "cohere.command-r-plus",
  "context_length": 4850,
  "response_length": 245,
  "execution_time_seconds": 3.2
}
```

### 3. Obtener Tipos de Auditoría

**GET** `/audit/audit-types`

Retorna información sobre los 7 tipos de auditoría disponibles.

#### Ejemplo de Response:

```json
{
  "audit_types": [
    {
      "type": "factura",
      "name": "Auditoría de Factura IPS",
      "description": "Verifica campos obligatorios de la factura médica: número, fecha, paciente, valor total, CUFE"
    },
    {
      "type": "historia_clinica",
      "name": "Auditoría de Historia Clínica",
      "description": "Analiza TRIAGE, motivo de consulta, diagnósticos, notas médicas, órdenes, epicrisis"
    }
  ],
  "total_types": 7,
  "description": "Tipos de auditoría médica especializada disponibles para accidentes de tránsito (AT/ECAT) en Colombia"
}
```

### 4. Obtener Decisiones de Auditoría

**GET** `/audit/audit-decisions`

Retorna las posibles decisiones finales según el Manual ADRES.

#### Ejemplo de Response:

```json
{
  "decisions": [
    {
      "decision": "Aprobada total",
      "description": "Todos los componentes de la auditoría cumplen con los requisitos. La cuenta médica es aprobada sin observaciones."
    },
    {
      "decision": "Aprobada parcial",
      "description": "La mayoría de componentes cumplen, pero hay observaciones menores que no impiden la aprobación."
    },
    {
      "decision": "Devuelta",
      "description": "Hay incumplimientos significativos que requieren corrección antes de la aprobación."
    },
    {
      "decision": "Anulada",
      "description": "La cuenta médica presenta fraudes o incumplimientos graves que impiden su procesamiento."
    }
  ],
  "total_decisions": 4,
  "description": "Posibles decisiones finales de auditoría médica según el Manual ADRES"
}
```

## Casos de Uso Comunes

### 1. Auditoría Completa de Cuenta Médica

```bash
curl -X POST "http://localhost:9000/audit/full-audit" \
-H "Authorization: Bearer YOUR_JWT_TOKEN" \
-H "Content-Type: application/json" \
-d '{
  "files_ids": [123, 456, 789],
  "k": 20,
  "max_context_chars": 10000,
  "run_master_audit": true
}'
```

### 2. Verificación Específica de Facturación

```bash
curl -X POST "http://localhost:9000/audit/question" \
-H "Authorization: Bearer YOUR_JWT_TOKEN" \
-H "Content-Type: application/json" \
-d '{
  "query": "¿Los medicamentos facturados tienen las órdenes médicas correspondientes con firmas válidas?",
  "files_ids": [123],
  "k": 15,
  "use_structured_output": true
}'
```

### 3. Análisis de Materiales Quirúrgicos

```bash
curl -X POST "http://localhost:9000/audit/question" \
-H "Authorization: Bearer YOUR_JWT_TOKEN" \
-H "Content-Type: application/json" \
-d '{
  "query": "¿Los materiales de osteosíntesis (MAOS) están debidamente facturados con documentación de proveedor válida?",
  "files_ids": [456, 789],
  "k": 10
}'
```

### 4. Auditoría Completa con Consultas Personalizadas

```bash
curl -X POST "http://localhost:9000/audit/full-audit" \
-H "Authorization: Bearer YOUR_JWT_TOKEN" \
-H "Content-Type: application/json" \
-d '{
  "files_ids": [123, 456, 789],
  "k": 15,
  "custom_queries": {
    "factura": "factura IPS número FAC-2024-001 valor total $4,246,800",
    "medicamentos": "paracetamol ibuprofeno dosis administración enfermería",
    "examenes": "radiografía torax laboratorio sangre hemograma",
    "procedimientos": "cirugía apendicectomía nota operatoria",
    "maos": "placa titanio tornillos osteosíntesis factura proveedor",
    "certificados": "SOAT póliza 123456 certificado policía"
  },
  "run_master_audit": true
}'
```

### 5. Recuperar Solo Contexto RAG (sin LLM)

```bash
curl -X POST "http://localhost:9000/audit/context-only" \
-H "Authorization: Bearer YOUR_JWT_TOKEN" \
-F "input=factura número FAC-2024-001" \
-F "files_ids=[123, 456]" \
-F "k=15"
```

## Códigos de Respuesta

- **200**: Auditoría ejecutada exitosamente
- **401**: Token de autenticación inválido o expirado
- **422**: Error de validación en los parámetros de entrada
- **500**: Error interno del servidor

## Notas Importantes

1. **Autenticación**: Todos los endpoints requieren autenticación JWT o API-KEY válida
2. **IDs de Archivos**: Los `files_ids` deben corresponder a archivos previamente procesados en la base de datos vectorial
3. **Contexto**: El parámetro `k` controla cuántos documentos similares se recuperan para el análisis
4. **Temperatura**: Valores bajos (0.1-0.3) dan respuestas más determinísticas, valores altos (0.7-1.0) más creativas
5. **Referencias de Página**: El sistema extrae y referencia páginas específicas usando formato "página X" o "pX"

## Integración con Base de Datos Vectorial

El servicio utiliza la base de datos vectorial autónoma de Oracle con embeddings para:

- Búsqueda semántica de contenido relevante
- Recuperación de contexto especializado por tipo de auditoría
- Análisis de similitud entre documentos médicos
- Filtrado por archivo específico usando `files_ids`

## 🔍 Cómo Funciona el Sistema RAG

### Flujo de Búsqueda Vectorial

El servicio de auditoría utiliza el mismo patrón que `rag_context.py`:

1. **`files_ids`**: Filtra la búsqueda a archivos específicos en la base de datos vectorial
2. **`input`/`search_query`**: La consulta de búsqueda semántica
3. **`k`**: Número de documentos similares a recuperar
4. **`OCIRAGTool.oci_vector_search_context_only()`**: Realiza la búsqueda vectorial

### Consultas Personalizadas vs. Predefinidas

#### **Consultas Predefinidas** (por defecto):
```python
search_queries = {
    "Factura": "factura médica número fecha emisión CUFE valor total detalle cargos",
    "Historia Clínica": "historia clínica triage motivo consulta diagnóstico notas médicas órdenes epicrisis",
    "Medicamentos": "órdenes médicas medicamentos administración enfermería firma médico CUM",
    # ... etc
}
```

#### **Consultas Personalizadas** (opcional):
```json
{
  "custom_queries": {
    "factura": "factura IPS número FAC-2024-001 valor total $4,246,800",
    "medicamentos": "paracetamol ibuprofeno dosis administración",
    "examenes": "radiografía torax laboratorio sangre"
  }
}
```

### Endpoint de Contexto RAG

**POST** `/audit/context-only` - Similar a `/rag/context` pero especializado para auditoría:

```bash
curl -X POST "http://localhost:9000/audit/context-only" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "input=factura número FAC-2024-001" \
  -F "files_ids=[123, 456]" \
  -F "k=15"
```

**Respuesta**:
```json
{
  "query": "factura número FAC-2024-001",
  "k_requested": 15,
  "total_documents": 8,
  "documents": [
    {
      "index": 1,
      "content": "Factura médica número FAC-2024-001...",
      "metadata": {...},
      "score": 0.95,
      "file_id": 123
    }
  ]
}
```

## Prompts Especializados

Cada tipo de auditoría utiliza prompts específicos optimizados para:

- **Factura**: Campos obligatorios, CUFE, valores monetarios
- **Historia Clínica**: TRIAGE, diagnósticos, evolución médica
- **Medicamentos**: Órdenes médicas, códigos CUM, administración
- **Exámenes**: Códigos CUPS, informes, órdenes médicas
- **Procedimientos**: Notas operatorias, personal médico, técnicas
- **MAOS**: Facturas de proveedor, comparación de valores (12% máximo)
- **Certificados**: Documentación legal, SOAT, certificados de autoridad

Todos los prompts están optimizados para el contexto colombiano y las regulaciones ADRES/SOAT.
