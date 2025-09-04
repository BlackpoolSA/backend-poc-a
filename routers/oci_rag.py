"""
API simplificada para la generación de embeddings desde OCI.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional

from schemas.oci_bucket import OCIObjectRAG, TextContentRequest
from schemas.oci_files import RAGFilesShema
from core.security import security_authenticate_user
from database import RAGFilesDB
from services.embedding import EmbeddingService

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()

@router.post(
    "/embedding",
    summary        = "Generar embeddings de un archivo desde OCI",
    description    = "Procesa un solo archivo desde OCI Object Storage y guarda los embeddings en Oracle ATP23ai.",
    response_model = OCIObjectRAG,
    tags           = ["RAG"]
)
def rag_embedding_endpoint(
    object_path : str = Query(..., description="Ruta del objecto en formato 'Bucket/prefix/file.ext'"),
    credentials : HTTPAuthorizationCredentials = Depends(security)
):
    """
    Ejecuta el pipeline de extracción y vectorización de un documento desde OCI hacia ATP23ai.
    """
    try:
        security_authenticate_user("/rag/embedding", credentials)

        embedding_service = EmbeddingService()
        result = embedding_service.process_file(object_path)

        return result

    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"[OCI][ERROR] Error en procesamiento OCI: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en procesamiento OCI: {str(e)}"
        )

@router.post(
    "/text-embedding",
    summary        = "Generar embeddings de contenido textual directamente",
    description    = "Procesa contenido textual directamente y genera embeddings sin requerir un archivo desde un bucket.",
    response_model = OCIObjectRAG,
    tags           = ["RAG"]
)
def rag_text_embedding_endpoint(
    request: TextContentRequest,
    credentials : HTTPAuthorizationCredentials = Depends(security)
):
    """
    Ejecuta el pipeline de extracción y vectorización de contenido textual directamente.
    """
    try:
        security_authenticate_user("/rag/text-embedding", credentials)

        embedding_service = EmbeddingService()
        result = embedding_service.process_text_content(
            text_content=request.text_content,
            file_name=request.file_name,
            file_trg_extraction=request.file_trg_extraction,
            file_trg_tot_pages=request.file_trg_tot_pages,
            file_trg_tot_characters=request.file_trg_tot_characters,
            file_trg_tot_time=request.file_trg_tot_time,
            file_trg_language=request.file_trg_language
        )

        return result

    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"[OCI][ERROR] Error en procesamiento de texto: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en procesamiento de texto: {str(e)}"
        )

@router.post(
    "/markdown-upload",
    summary        = "Subir archivo markdown y generar embeddings",
    description    = "Sube un archivo markdown y genera embeddings. Acepta archivos via FormData.",
    response_model = OCIObjectRAG,
    tags           = ["RAG"]
)
async def rag_markdown_upload_endpoint(
    file: UploadFile = File(..., description="Archivo markdown a subir"),
    file_name: Optional[str] = Form(None, description="Nombre personalizado del archivo"),
    file_trg_extraction: Optional[str] = Form(None, description="Contenido extraído del archivo (se auto-llena si no se proporciona)"),
    file_trg_tot_pages: Optional[int] = Form(1, description="Número de páginas del documento"),
    file_trg_tot_characters: Optional[int] = Form(None, description="Número de caracteres del documento"),
    file_trg_tot_time: Optional[str] = Form("00:00:00", description="Tiempo de procesamiento del documento"),
    file_trg_language: Optional[str] = Form("esa", description="Idioma del documento"),
    credentials : HTTPAuthorizationCredentials = Depends(security)
):
    """
    Sube un archivo markdown y ejecuta el pipeline de extracción y vectorización.
    El contenido del archivo se extrae automáticamente como file_trg_extraction.
    """
    try:
        security_authenticate_user("/rag/markdown-upload", credentials)

        # Validar que sea un archivo markdown
        if not file.filename.lower().endswith(('.md', '.markdown')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Solo se aceptan archivos markdown (.md, .markdown)"
            )

        # Leer contenido del archivo
        content = await file.read()
        content_str = content.decode('utf-8')
                
        # Usar nombre personalizado o del archivo
        name = file_name or file.filename
        
        # Auto-llenar file_trg_extraction con el contenido del archivo si no se proporciona o está vacío
        if file_trg_extraction is None or file_trg_extraction.strip() == "":
            file_trg_extraction = content_str
            logger.info(f"[OCI][RAG] Auto-llenando file_trg_extraction con contenido del archivo")
        else:
            logger.info(f"[OCI][RAG] Usando file_trg_extraction proporcionado")

        logger.info(f"[OCI][RAG] file_trg_extraction length: {len(file_trg_extraction) if file_trg_extraction else 0}")
        logger.info(f"[OCI][RAG] file_trg_extraction preview: {file_trg_extraction[:100] if file_trg_extraction else 'None'}...")

        embedding_service = EmbeddingService()
        result = embedding_service.process_markdown_file(
            file_content=content_str,
            file_name=name,
            file_trg_extraction=file_trg_extraction,
            file_trg_tot_pages=file_trg_tot_pages,
            file_trg_tot_characters=file_trg_tot_characters,
            file_trg_tot_time=file_trg_tot_time,
            file_trg_language=file_trg_language
        )

        return result

    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"[OCI][ERROR] Error en subida de archivo markdown: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en subida de archivo markdown: {str(e)}"
        )

@router.get(
    "/files",
    summary="Obtener todos los archivos con embeddings",
    description="Devuelve una lista de todos los archivos que han sido procesados y tienen embeddings.",
    response_model=List[RAGFilesShema],
    tags=["RAG"]
)
def get_all_files_with_embeddings(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Endpoint para obtener todos los archivos con embeddings de la base de datos.
    """
    try:
        security_authenticate_user("/rag/files", credentials)
        embedding_service = EmbeddingService()
        files_dict = embedding_service.get_embeddings_status()
        
        # El diccionario de valores ya cumple con el esquema RAGFilesShema
        return list(files_dict.values())
        
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"[OCI][RAG] Error al obtener archivos con embeddings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener archivos con embeddings: {str(e)}"
        )


@router.delete(
    "/embedding/delete/{file_id}",
    summary="Eliminar embeddings de un archivo",
    description=(
        "Elimina los registros de embeddings de un archivo específico "
        "de las tablas rag_docs y rag_files en ese orden."
    ),
    tags=["RAG"]
)
async def delete_file_embeddings(
    file_id: int,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Elimina los embeddings de un archivo específico.
    """
    try:
        security_authenticate_user("rag/embedding/delete/{file_id}", credentials)
                
        # Eliminar registros
        rag_files = RAGFilesDB()
        success = rag_files.delete_file_with_docs(file_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al eliminar el embedding del file_id: {file_id}: {str(e)}"
            )
        
        return {"message": "Registros eliminados exitosamente.", "file_id": file_id}

    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"[OCI][BUK] Error al eliminar el embedding del file_id: {file_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar el embedding del file_id: {file_id}: {str(e)}"
        )

