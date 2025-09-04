# Usar Python 3.11 slim como base
FROM python:3.11-slim

# Establecer directorio de trabajo
WORKDIR /app

# Instalar solo dependencias mínimas del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements.txt primero para aprovechar la caché de Docker
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY . .

# Crear directorio para archivos temporales
RUN mkdir -p temp

# Exponer puerto
EXPOSE 9000

# Comando para ejecutar la aplicación
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
