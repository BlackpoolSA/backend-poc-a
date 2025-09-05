"""
Router para el sistema de agentes de DeepAgents.
"""

import logging
import json
import time

from typing import List, Optional
from pathlib import Path
from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    status,
    File,
    UploadFile,
)
from starlette.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.security import security_authenticate_user
from services.ocr_mineru import process_file as ocr_process_file
from services.agent import agent
from services.tools.oci_xml_ubl_tool import OCIXMLUBLTool
from fastapi.responses import StreamingResponse
from utils.utils import Utils
from core.config import settings


logger = logging.getLogger(__name__)
router = APIRouter()
xml_ubl_tool = OCIXMLUBLTool()
security = HTTPBearer()
utils = Utils()


@router.post(
    "/files",
    summary="Procesar archivo ZIP y devolver agent_request",
    description="Recibe archivo ZIP, lo procesa (OCR/XML/PDF) y devuelve la estructura agent_request para ser usada en /agent/process",
    tags=["Agent"],
)
async def files_endpoint(
    files: List[UploadFile] = File(..., description="Archivos adjuntos a procesar"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Procesa archivos y devuelve un agent_request listo para /agent/process."""
    try:
        security_authenticate_user("/agent/files", credentials)

        # Validación: DEBE ser exactamente 1 archivo ZIP
        uploaded_names = [(f.filename or "").strip().lower() for f in (files or [])]
        zip_count = sum(1 for n in uploaded_names if n.endswith(".zip"))
        if len(uploaded_names) != 1 or zip_count != 1:
            detail_msg = (
                "Se requiere exactamente 1 archivo: 1 '.zip'"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=detail_msg
            )

        files_processed, files_metadata = await utils.process_uploaded_files(
            files or [], temp_dir_name=".agent_files"
        )
        if files_processed:
            logger.info(
                f"[DEEP_AGENTS][FILES] Archivos Detectado(s): {len(files_processed)} [SUCCESS]"
            )

        processed_files = {}

        # Si hay ZIPs, usar utilidad para descomprimir a la carpeta temporal configurada
        try:
            extra_files_metadata = []
            for file_info in files_metadata:
                filename = file_info["filename"]
                if Path(filename).suffix.lower() == ".zip":
                    zip_path = Path(file_info["temp_path"]).resolve()
                    # Ejecutar extracción en threadpool para no bloquear el event loop
                    extracted = await run_in_threadpool(
                        utils.extract_zip_to_temp, zip_path, ".agent_files"
                    )
                    extra_files_metadata.extend(extracted)
            if extra_files_metadata:
                files_metadata.extend(extra_files_metadata)
        except Exception as _e:
            logger.warning(f"[DEEP_AGENTS][FILES][ZIP] Error al descomprimir: {_e}")

        # 1. ZIP (solo registrar, no procesar contenido en esta versión)
        for file_info in files_metadata:
            filename = file_info["filename"]
            file_extension = Path(filename).suffix.lower()
            if file_extension == ".zip":
                logger.info(
                    f"[DEEP_AGENTS][FILES][ZIP] Archivo: [{filename}] [DETECTED]"
                )

        # 2. XML
        for file_info in files_metadata:
            filename = file_info["filename"]
            file_extension = Path(filename).suffix.lower()
            if file_extension == ".xml":
                with open(file_info["temp_path"], "r", encoding="utf-8") as f:
                    xml_content = f.read()
                files_dict = {filename: xml_content}
                # Procesamiento XML potencialmente costoso → threadpool
                processed_json = await run_in_threadpool(
                    xml_ubl_tool.process_ubl_xml, filename, files_dict
                )
                processed_files[f"{Path(filename).stem}_xml.json"] = processed_json
                logger.info(
                    f"[DEEP_AGENTS][FILES][XML] Archivo: [{filename}] [SUCCESS]"
                )

        # 3. PDF
        for file_info in files_metadata:
            filename = file_info["filename"]
            file_extension = Path(filename).suffix.lower()
            if file_extension == ".pdf":
                # OCR bloqueante → threadpool para no bloquear otras solicitudes
                ocr_result = await run_in_threadpool(
                    ocr_process_file, Path(file_info["temp_path"])
                )
                processed_files[filename] = ocr_result.get("file_trg_extraction", "")

                # Guardar el contenido del markdown para que esté disponible en /glosa y /process
                markdown_content = ocr_result.get("markdown_content")
                if markdown_content:
                    processed_files["upload.md"] = markdown_content
                    logger.info(
                        f"[DEEP_AGENTS][FILES][OCR] upload.md guardado para: [{filename}] [SUCCESS]"
                    )

                # Procesar resultado de auditoría si está disponible
                audit_result = ocr_result.get("audit_result")
                if audit_result:
                    processed_files[f"{filename}_audit_result.json"] = json.dumps(
                        audit_result, ensure_ascii=False
                    )
                    logger.info(
                        f"[DEEP_AGENTS][FILES][AUDIT] Auditoría procesada para: [{filename}] [SUCCESS]"
                    )

                logger.info(
                    f"[DEEP_AGENTS][FILES][OCR] Archivo: [{filename}] [SUCCESS]"
                )

        agent_request = {"files": processed_files}
        logger.info(
            f"[DEEP_AGENTS][FILES] Procesamiento finalizado [files={len(processed_files)}] [SUCCESS]"
        )

        return {"agent_request": agent_request}

    except Exception as e:
        logger.error(f"[DEEP_AGENTS][FILES] Error procesando archivos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error procesando archivos: {str(e)}",
        )


@router.post(
    "/glosa",
    summary="Procesar archivo ZIP y ejecutar auditoría médica",
    description="""
    Recibe archivo ZIP, lo procesa y ejecuta la auditoría médica completa.
    
    Modo Normal: Procesa ZIP con PDF → OCR Mineru → Markdown → Vectorización → Auditoría
    Modo Pruebas: Feature flag `use_local_md=true` para cargar archivo MD del disco
    
    Parámetros del Feature Flag (Opcionales con Optional):
    - `use_local_md: Optional[bool]`: Activa modo archivo local (default: false)
    - `local_md_path: Optional[str]`: Ruta al archivo MD local (default: "test_data/sample_audit.md")
    
    Nota: Los parámetros del feature flag son completamente opcionales usando Pydantic Optional. 
    Si no se proporcionan o son None, se usan los valores por defecto.
    """,
    tags=["Agent"],
)
async def glosa_endpoint(
    files: List[UploadFile] = File(..., description="Archivos adjuntos a procesar"),
    use_local_md: Optional[bool] = File(False, description="Feature flag para usar archivo MD local (opcional)"),
    local_md_path: Optional[str] = File("test_data/sample_audit.md", description="Ruta al archivo MD local (opcional)"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Procesa archivos y ejecuta auditoría."""
    # Iniciar timing completo del request
    request_start_time = time.time()
    
    try:
        security_authenticate_user("/agent/glosa", credentials)

        # Validación: DEBE ser exactamente 1 archivo ZIP
        uploaded_names = [(f.filename or "").strip().lower() for f in (files or [])]
        zip_count = sum(1 for n in uploaded_names if n.endswith(".zip"))
        if len(uploaded_names) != 1 or zip_count != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Se requiere exactamente 1 archivo: 1 '.zip'",
            )

        # Procesar archivos directamente (sin llamar a files_endpoint)
        files_processed, files_metadata = await utils.process_uploaded_files(
            files or [], temp_dir_name=".agent_files"
        )
        if files_processed:
            logger.info(
                f"[DEEP_AGENTS][GLOSA] Archivos Detectado(s): {len(files_processed)} [SUCCESS]"
            )

        processed_files = {}
        zip_filename = None  # Para capturar el nombre del archivo ZIP

        # Si hay ZIPs, usar utilidad para descomprimir a la carpeta temporal configurada
        try:
            extra_files_metadata = []
            for file_info in files_metadata:
                filename = file_info["filename"]
                if Path(filename).suffix.lower() == ".zip":
                    # Capturar el nombre del archivo ZIP (sin extensión)
                    zip_filename = Path(filename).stem
                    logger.info(f"[DEEP_AGENTS][GLOSA] Archivo ZIP detectado: {filename} -> identificacion: {zip_filename}")
                    
                    zip_path = Path(file_info["temp_path"]).resolve()
                    # Ejecutar extracción en threadpool para no bloquear el event loop
                    extracted = await run_in_threadpool(
                        utils.extract_zip_to_temp, zip_path, ".agent_files"
                    )
                    extra_files_metadata.extend(extracted)
            if extra_files_metadata:
                files_metadata.extend(extra_files_metadata)
        except Exception as _e:
            logger.warning(f"[DEEP_AGENTS][GLOSA][ZIP] Error al descomprimir: {_e}")

        # Feature flag: usar archivo MD local para pruebas
        if use_local_md is True:
            logger.info(f"[DEEP_AGENTS][GLOSA][FEATURE_FLAG] 🚀 MODO PRUEBAS ACTIVADO")
            logger.info(f"[DEEP_AGENTS][GLOSA][FEATURE_FLAG] Archivo MD local: {local_md_path}")
            logger.info(f"[DEEP_AGENTS][GLOSA][FEATURE_FLAG] Saltando OCR Mineru → Cargando archivo del disco")
            
            try:
                # Validar que local_md_path no sea None
                if local_md_path is None:
                    local_md_path = "test_data/sample_audit.md"
                    logger.info(f"[DEEP_AGENTS][GLOSA][FEATURE_FLAG] local_md_path era None, usando valor por defecto: {local_md_path}")
                
                # Construir ruta completa relativa al proyecto
                project_root = Path(__file__).parent.parent
                local_file_path = project_root / local_md_path
                
                if not local_file_path.exists():
                    raise FileNotFoundError(f"Archivo local no encontrado: {local_file_path}")
                
                # Leer contenido del archivo markdown local
                with open(local_file_path, "r", encoding="utf-8") as f:
                    local_md_content = f.read()
                
                if not local_md_content.strip():
                    raise ValueError("Archivo local está vacío")
                
                processed_files["upload.md"] = local_md_content
                logger.info(
                    f"[DEEP_AGENTS][GLOSA][FEATURE_FLAG] Archivo local cargado exitosamente. Tamaño: {len(local_md_content)} caracteres"
                )
                
            except Exception as local_error:
                logger.error(f"[DEEP_AGENTS][GLOSA][FEATURE_FLAG] Error cargando archivo local: {str(local_error)}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Error cargando archivo local: {str(local_error)}"
                )
        else:
            # Procesar solo PDFs para obtener upload.md (flujo normal)
            for file_info in files_metadata:
                filename = file_info["filename"]
                file_extension = Path(filename).suffix.lower()
                if file_extension == ".pdf":
                    # OCR bloqueante → threadpool para no bloquear otras solicitudes
                    ocr_result = await run_in_threadpool(
                        ocr_process_file, Path(file_info["temp_path"])
                    )

                    # Guardar el contenido del markdown para la auditoría
                    markdown_content = ocr_result.get("markdown_content")
                    if markdown_content:
                        processed_files["upload.md"] = markdown_content
                        logger.info(
                            f"[DEEP_AGENTS][GLOSA][OCR] upload.md obtenido de: [{filename}] [SUCCESS]"
                        )
                        break  # Solo necesitamos el primer PDF

        # Buscar upload.md y vectorizarlo para obtener file_id
        upload_md_content = processed_files.get("upload.md")

        if upload_md_content:
            logger.info(f"[DEEP_AGENTS][GLOSA] Vectorizando contenido markdown del OCR")

            try:
                # Vectorizar el contenido markdown usando el servicio de embedding
                from services.embedding import EmbeddingService

                embedding_service = EmbeddingService()

                # Vectorizar el contenido markdown directamente
                vectorization_result = await run_in_threadpool(
                    embedding_service.process_markdown_file, 
                    upload_md_content,  # Contenido markdown del OCR
                    "glosa_audit.md"    # Nombre del archivo
                )

                # Obtener el file_id del resultado
                file_id = vectorization_result.get("file_id")
                if not file_id:
                    raise Exception("No se pudo obtener file_id de la vectorización")

                logger.info(
                    f"[DEEP_AGENTS][GLOSA] Contenido vectorizado exitosamente. File ID: {file_id}"
                )

                # Ejecutar auditoría médica completa usando el file_id
                from services.audit import MedicalAuditService

                audit_service = MedicalAuditService()

                logger.info(
                    f"[DEEP_AGENTS][GLOSA] Ejecutando auditoría médica completa para file_id: {file_id}"
                )

                audit_result = await run_in_threadpool(
                    audit_service.run_full_medical_audit,
                    files_ids=[file_id],
                    k=15,
                    max_context_chars=8000,
                    run_master_audit=True,
                    response_format="v2",  # Usar formato v2 para JSON schema
                    identificacion_reclamacion=zip_filename
                )



                logger.info(
                    f"[DEEP_AGENTS][GLOSA] Auditoría médica completada exitosamente"
                )
                
                # Calcular tiempo total del request
                total_request_time = time.time() - request_start_time
                
                # Agregar tiempo total del request a la respuesta
                if hasattr(audit_result, 'dict'):
                    # Si es un objeto Pydantic, convertir a dict y agregar el campo
                    result_dict = audit_result.dict()
                    result_dict['total_request_time_seconds'] = total_request_time
                    return result_dict
                elif isinstance(audit_result, dict):
                    # Si ya es un dict, agregar directamente
                    audit_result['total_request_time_seconds'] = total_request_time
                    return audit_result
                else:
                    # Fallback: retornar el resultado original
                    return audit_result

            except Exception as audit_error:
                total_request_time = time.time() - request_start_time
                logger.error(
                    f"[DEEP_AGENTS][GLOSA] Error en auditoría médica: {str(audit_error)} (Tiempo total: {total_request_time:.2f}s)"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error ejecutando auditoría médica: {str(audit_error)}",
                )

        # Si no se encontró upload.md, devolver error
        if not upload_md_content:
            total_request_time = time.time() - request_start_time
            logger.warning(
                f"[DEEP_AGENTS][GLOSA] No se encontró upload.md - no se puede ejecutar auditoría (Tiempo total: {total_request_time:.2f}s)"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se encontró upload.md - no se puede ejecutar auditoría",
            )

    except HTTPException:
        raise
    except Exception as e:
        total_request_time = time.time() - request_start_time
        logger.error(f"[DEEP_AGENTS][GLOSA] Error en glosa: {str(e)} (Tiempo total: {total_request_time:.2f}s)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en glosa: {str(e)}",
        )


@router.post(
    "/process",
    summary="Procesar archivo ZIP y ejecutar auditoría con streaming",
    description="Recibe archivo ZIP, lo procesa y ejecuta la auditoría con glosas en streaming",
    tags=["Agent"],
)
async def process_endpoint(
    files: List[UploadFile] = File(..., description="Archivos adjuntos a procesar"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Procesa archivos y ejecuta auditoría con streaming."""
    try:
        security_authenticate_user("/agent/process", credentials)

        # Validación: DEBE ser exactamente 1 archivo ZIP
        uploaded_names = [(f.filename or "").strip().lower() for f in (files or [])]
        zip_count = sum(1 for n in uploaded_names if n.endswith(".zip"))
        if len(uploaded_names) != 1 or zip_count != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Se requiere exactamente 1 archivo: 1 '.zip'",
            )

        # Procesar archivos directamente (sin llamar a files_endpoint)
        files_processed, files_metadata = await utils.process_uploaded_files(
            files or [], temp_dir_name=".agent_files"
        )
        if files_processed:
            logger.info(
                f"[DEEP_AGENTS][PROCESS] Archivos Detectado(s): {len(files_processed)} [SUCCESS]"
            )

        processed_files = {}
        zip_filename_process = None  # Para capturar el nombre del archivo ZIP

        # Si hay ZIPs, usar utilidad para descomprimir a la carpeta temporal configurada
        try:
            extra_files_metadata = []
            for file_info in files_metadata:
                filename = file_info["filename"]
                if Path(filename).suffix.lower() == ".zip":
                    # Capturar el nombre del archivo ZIP (sin extensión)
                    zip_filename_process = Path(filename).stem
                    logger.info(f"[DEEP_AGENTS][PROCESS] Archivo ZIP detectado: {filename} -> identificacion: {zip_filename_process}")
                    
                    zip_path = Path(file_info["temp_path"]).resolve()
                    # Ejecutar extracción en threadpool para no bloquear el event loop
                    extracted = await run_in_threadpool(
                        utils.extract_zip_to_temp, zip_path, ".agent_files"
                    )
                    extra_files_metadata.extend(extracted)
            if extra_files_metadata:
                files_metadata.extend(extra_files_metadata)
        except Exception as _e:
            logger.warning(f"[DEEP_AGENTS][PROCESS][ZIP] Error al descomprimir: {_e}")

        # Procesar solo PDFs para obtener upload.md
        for file_info in files_metadata:
            filename = file_info["filename"]
            file_extension = Path(filename).suffix.lower()
            if file_extension == ".pdf":
                # OCR bloqueante → threadpool para no bloquear otras solicitudes
                ocr_result = await run_in_threadpool(
                    ocr_process_file, Path(file_info["temp_path"])
                )

                # Guardar el contenido del markdown para la auditoría
                markdown_content = ocr_result.get("markdown_content")
                if markdown_content:
                    processed_files["upload.md"] = markdown_content
                    logger.info(
                        f"[DEEP_AGENTS][PROCESS][OCR] upload.md obtenido de: [{filename}] [SUCCESS]"
                    )
                    break  # Solo necesitamos el primer PDF

        logger.info(
            f"[DEEP_AGENTS][PROCESS] Iniciando proceso... [files={len(processed_files)}] [START]"
        )

        async def generate_stream():
            # Solo enviar el resultado de auditoría, sin el agente
            upload_md_content = processed_files.get("upload.md")
            if upload_md_content:
                logger.info(f"[DEEP_AGENTS][PROCESS] Vectorizando contenido markdown del OCR")
                
                try:
                    # Vectorizar el contenido markdown usando el servicio de embedding
                    from services.embedding import EmbeddingService
                    from services.audit import MedicalAuditService
                    
                    embedding_service = EmbeddingService()
                    audit_service = MedicalAuditService()
                    
                    # Vectorizar el contenido markdown directamente
                    vectorization_result = await run_in_threadpool(
                        embedding_service.process_markdown_file, 
                        upload_md_content,  # Contenido markdown del OCR
                        "process_audit.md"  # Nombre del archivo
                    )
                    
                    # Obtener el file_id del resultado
                    file_id = vectorization_result.get("file_id")
                    if not file_id:
                        raise Exception("No se pudo obtener file_id de la vectorización")
                    
                    logger.info(f"[DEEP_AGENTS][PROCESS] Contenido vectorizado. File ID: {file_id}")
                    
                    # Ejecutar auditoría médica completa usando el file_id
                    audit_result = await run_in_threadpool(
                        audit_service.run_full_medical_audit,
                        files_ids=[file_id],
                        k=15,
                        max_context_chars=8000,
                        run_master_audit=True,
                        response_format="v2",  # Usar formato v2 para JSON schema
                        identificacion_reclamacion=zip_filename_process
                    )
                    
                    logger.info(f"[DEEP_AGENTS][PROCESS] Auditoría médica completada")
                    
                    # Enviar solo el resultado de auditoría
                    audit_chunk = {"type": "audit_result", "audit_data": audit_result}
                    yield json.dumps(audit_chunk) + "\n"
                    
                except Exception as audit_error:
                    logger.error(f"[DEEP_AGENTS][PROCESS] Error en auditoría: {str(audit_error)}")
                    error_chunk = {
                        "type": "error",
                        "message": f"Error ejecutando auditoría médica: {str(audit_error)}",
                    }
                    yield json.dumps(error_chunk) + "\n"
            else:
                logger.warning(
                    "[DEEP_AGENTS][PROCESS] No se encontró upload.md - no se puede ejecutar auditoría"
                )
                error_chunk = {
                    "type": "error",
                    "message": "No se encontró upload.md - no se puede ejecutar auditoría",
                }
                yield json.dumps(error_chunk) + "\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DEEP_AGENTS][PROCESS] Error en streaming: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en streaming: {str(e)}",
        )
