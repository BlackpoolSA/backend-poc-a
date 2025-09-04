"""
Router para la exploración de OCI Object Storage.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from schemas.oci_bucket import OCIObjectListResponse
from core.security import security_authenticate_user
from services.oci_bucket import OCIClient

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()

@router.get(
    "/bucket/list",
    summary        = "Listar contenido de un bucket de OCI",
    description    = "Obtiene una lista estructurada de archivos y carpetas para una ruta de bucket específica, junto con un conteo de tipos de archivo.",
    response_model = OCIObjectListResponse,
    tags           = ["Bucket"]
)
def oci_bucket_list_endpoint(
    bucket_path : str = Query(..., description="Ruta del bucket a explorar en formato 'Bucket/prefix/'"),
    credentials : HTTPAuthorizationCredentials = Depends(security)
):
    """
    Endpoint para explorar el contenido de un bucket en OCI.
    """
    try:
        security_authenticate_user("/oci/bucket/list", credentials)
        
        oci_client = OCIClient()
        bucket_name, prefix = oci_client.validate_bucket_path(bucket_path)        
        response = oci_client.list_structured_bucket_contents(bucket_name, prefix)
        
        return response
        
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"[OCI][BUK] Error al listar el contenido del Bucket {bucket_path}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar el contenido del Bucket {bucket_path}: {e}"
        )

