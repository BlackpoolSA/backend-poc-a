# Manifests de Kubernetes para ADRES Backend

Este directorio contiene los manifests de Kubernetes organizados en archivos separados para mejor mantenimiento y claridad.

## 📁 Estructura de archivos

```
k8s/
├── 01-namespace.yaml      # Namespace del backend
├── 02-secret.yaml         # Variables de entorno sensibles
├── 03-deployment.yaml     # Deployment del servicio
├── 04-service.yaml        # Service (LoadBalancer)
├── 05-ingress.yaml        # Ingress (opcional)
└── README.md             # Este archivo
```

## 🚀 Despliegue

### Opción 1: Desplegar archivos individuales (recomendado)

```bash
# Aplicar en orden
kubectl apply -f 01-namespace.yaml
kubectl apply -f 02-secret.yaml
kubectl apply -f 03-deployment.yaml
kubectl apply -f 04-service.yaml
kubectl apply -f 05-ingress.yaml  # Opcional
```

### Opción 2: Desplegar todo de una vez

```bash
kubectl apply -f .
```


## ⚙️ Configuración previa

### 1. Actualizar variables de entorno

Edita `02-secret.yaml` y reemplaza todos los placeholders:

```yaml
SECRET_KEY: "tu-clave-secreta-real"
AUTH_CLIENT_ID: "tu-client-id"
# ... etc
```

### 2. Configurar imagen Docker

En `03-deployment.yaml`, actualiza la imagen:

```yaml
image: us-chicago-1.ocir.io/your-tenancy/repo/adres-backend:latest
```

### 3. Configurar dominio (opcional)

En `05-ingress.yaml`, actualiza el dominio:

```yaml
- host: api.tu-dominio.com
```

## 🔍 Verificación del despliegue

```bash
# Verificar pods
kubectl get pods -n backend

# Verificar servicios
kubectl get svc -n backend

# Verificar logs
kubectl logs -f deployment/adres-backend -n backend

# Verificar health check
kubectl port-forward svc/adres-backend-service 9000:9000 -n backend
curl http://localhost:9000/sys/health
```

## 🛠️ Comandos útiles

```bash
# Escalar deployment
kubectl scale deployment adres-backend --replicas=3 -n backend

# Actualizar imagen
kubectl set image deployment/adres-backend adres-backend=us-chicago-1.ocir.io/your-tenancy/repo/adres-backend:v2.0 -n backend

# Eliminar todo
kubectl delete -f .
```

## 📋 Recursos creados

- **Namespace**: `backend`
- **Secret**: `adres-backend-secret`
- **Deployment**: `adres-backend` (1 replica)
- **Service**: `adres-backend-service` (LoadBalancer)
- **Ingress**: `adres-backend-ingress` (opcional)

## 🔒 Seguridad

- El contenedor se ejecuta como usuario no-root (UID 1000)
- Privilegios de escalación deshabilitados
- Todas las capabilities eliminadas
- Variables sensibles en Secret (no en ConfigMap)

## 📊 Recursos solicitados

- **CPU**: 4000m (4 cores)
- **Memoria**: 16Gi
- **Puerto**: 9000
