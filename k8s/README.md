# Manifests de Kubernetes para ADRES Backend

Este directorio contiene los manifests de Kubernetes organizados en archivos separados para mejor mantenimiento y claridad.

## 📁 Estructura de archivos

```
k8s/
├── 01-namespace.yaml              # Namespace del backend
├── 02-persistent-volumes.yaml     # PersistentVolumes para volúmenes
├── 03-persistent-volume-claims.yaml # PersistentVolumeClaims
├── 04-secret.yaml                 # Variables de entorno sensibles
├── 05-deployment.yaml             # Deployment del servicio
├── 06-service.yaml                # Service (LoadBalancer)
├── 07-ingress.yaml                # Ingress (opcional)
└── README.md                      # Este archivo
```

## 🚀 Despliegue

### Opción 1: Desplegar archivos individuales (recomendado)

```bash
# Aplicar en orden
kubectl apply -f 01-namespace.yaml
kubectl apply -f 02-persistent-volumes.yaml
kubectl apply -f 03-persistent-volume-claims.yaml
kubectl apply -f 04-secret.yaml
kubectl apply -f 05-deployment.yaml
kubectl apply -f 06-service.yaml
kubectl apply -f 07-ingress.yaml  # Opcional
```

### Opción 2: Desplegar todo de una vez

```bash
kubectl apply -f .
```


## 💾 Volúmenes Persistentes

El backend de ADRES requiere tres volúmenes persistentes:

- **`temp`** (10Gi): Directorio temporal para archivos de procesamiento
- **`wallet`** (1Gi): Wallet de Oracle Database para conexiones ATP
- **`oci`** (100Mi): Configuración de OCI (certificados, configs)

### Configuración de volúmenes

Los volúmenes se configuran como `hostPath` por defecto. Para producción, considera usar:

- **NFS**: Para volúmenes compartidos entre nodos
- **CSI drivers**: Para volúmenes gestionados por el proveedor de nube
- **Local storage**: Para volúmenes locales de alto rendimiento

### Verificar volúmenes

```bash
# Ver PersistentVolumes
kubectl get pv

# Ver PersistentVolumeClaims
kubectl get pvc -n backend

# Verificar montaje en el pod
kubectl exec -it deployment/adres-backend -n backend -- ls -la /app/
```

## ⚙️ Configuración previa

### 1. Actualizar variables de entorno

Edita `04-secret.yaml` y reemplaza todos los placeholders:

```yaml
SECRET_KEY: "tu-clave-secreta-real"
AUTH_CLIENT_ID: "tu-client-id"
# ... etc
```

### 2. Configurar imagen Docker

En `05-deployment.yaml`, actualiza la imagen:

```yaml
image: us-chicago-1.ocir.io/your-tenancy/repo/adres-backend:latest
```

### 3. Configurar dominio (opcional)

En `07-ingress.yaml`, actualiza el dominio:

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
- **PersistentVolumes**: `adres-backend-temp-pv`, `adres-backend-wallet-pv`, `adres-backend-oci-pv`
- **PersistentVolumeClaims**: `adres-backend-temp-pvc`, `adres-backend-wallet-pvc`, `adres-backend-oci-pvc`
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
