import sys
import os
import logging
from logging import Filter
import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Añadir el directorio raíz del proyecto al sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings
from routers import (
    chat,
    agent,
    system,
    oci_rag,
    oci_bucket,
    auth,
    llm,
    rag_context
)

# --- Inicio: Filtro para logs de asyncio ---
class SocketSendFilter(Filter):
    def filter(self, record):
        return "socket.send() raised exception." not in record.getMessage()

# Aplicar filtro al logger de asyncio
asyncio_logger = logging.getLogger("asyncio")
asyncio_logger.addFilter(SocketSendFilter())
# --- Fin: Filtro para logs de asyncio ---


# Configuración de logging
logging.getLogger().handlers = [] # Limpiar Handlers existentes
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger()

# Handler para el archivo de auditoría
file_handler = logging.FileHandler('audit.log', mode='a')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Crear aplicación FastAPI
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=settings.API_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configurar CORS (esta es la forma preferida y más robusta)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Manejador de excepciones global para asegurar cabeceras CORS en errores
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS, DELETE, PUT",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )

# Manejador de validaciones (evitar decodificar bytes de multipart en mensajes de error)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": f"Solicitud inválida: {exc.errors()}" 
        },
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS, DELETE, PUT",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )

# Incluir todos los routers modulares
app.include_router(system.router, prefix="/sys")
app.include_router(oci_rag.router, prefix="/rag")
app.include_router(rag_context.router, prefix="/rag")
app.include_router(oci_bucket.router, prefix="/oci")
app.include_router(auth.router, prefix="/auth")
app.include_router(chat.router, prefix="/chat")
app.include_router(agent.router, prefix="/agent")
app.include_router(llm.router, prefix="/llm")



if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9000,
        reload=False,
        log_level=settings.LOG_LEVEL.lower()
    )
