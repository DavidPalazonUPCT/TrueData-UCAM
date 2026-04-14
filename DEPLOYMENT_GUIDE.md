# Guía de Despliegue y Operación - FlowGuard

Esta guía detalla los pasos necesarios para desplegar, configurar y operar el sistema FlowGuard. Está diseñada para ser copiada y utilizada como documentación oficial del proyecto.

## 1. Requisitos Previos

Antes de comenzar, asegúrese de tener instalado y configurado lo siguiente en su servidor o máquina local:
*   **Docker Engine** y **Docker Compose**.
*   Acceso a una terminal con permisos de superusuario (`sudo`).
*   La estructura de carpetas del proyecto debe estar completa (ver `README.md` del proyecto).

---

## 2. Preparación del Entorno

Es crítico configurar la red y los permisos antes de levantar cualquier contenedor.

### 2.1. Creación de la Red Docker
El sistema utiliza una red dedicada con una subred específica para asignar IPs estáticas a los servicios clave (ThingsBoard, Node-RED).

```bash
docker network create --driver=bridge --subnet=172.25.0.0/24 flowguard-compose_iot_network
```

### 2.2. Configuración de Permisos
ThingsBoard requiere permisos específicos de escritura en sus carpetas de volúmenes para inicializar la base de datos correctamente.

```bash
# Dar permisos generales a la carpeta de ThingsBoard
sudo chmod -R 777 tb

# Dar permisos restrictivos pero suficientes a la base de datos (evita errores de inicio de Postgres)
sudo chmod 750 tb/data/db
```

### 2.3. Configuración de Credenciales de Node-RED
1.  Localice el archivo `settings.js` en la raíz del proyecto.
2.  Edite las secciones `adminAuth` y `credentialSecret` con sus contraseñas deseadas.
3.  Copie este archivo a la carpeta de datos de Node-RED:
    ```bash
    cp settings.js nodered/data/settings.js
    ```

---

## 3. Despliegue de Infraestructura

Levante los servicios principales (Node-RED, ThingsBoard, PostgreSQL, Servicio de Inferencia).

```bash
docker-compose up --build -d
```
*   El flag `-d` ejecuta el proceso en segundo plano.
*   Espere unos minutos a que ThingsBoard inicialice su base de datos completamente.

**Verificación:**
Acceda a `http://localhost:9090` (ThingsBoard) y `http://localhost:1880` (Node-RED) para asegurar que responden.

---

## 4. Inicialización del Cliente

Una vez que la infraestructura está operativa, se debe inyectar la configuración del cliente (flujos, dispositivos, buckets, etc.).

**Nota:** Revise el archivo `deploy/Client.json` para asegurar que el nombre del cliente y el modelo son correctos.

Ejecute el script maestro de configuración:
```bash
python3 deploy/env_client.py
```

Este script automatiza los siguientes pasos:
1.  **Configuración General:** Variables globales.
2.  **Niveles de Criticidad:** Carga inicial a ThingsBoard.
3.  **Dispositivos:** Creación de entidades en ThingsBoard.
4.  **Flujos Node-RED:** Despliegue de pipelines ETL en Node-RED.
5.  **Umbrales (Thresholds):** Carga de parámetros del modelo a ThingsBoard.

---

## 5. Operación: Entrenamiento (Retraining)

El re-entrenamiento del modelo se ejecuta en un contenedor efímero dedicado. Este proceso incluye la generación de nuevos datos y el ajuste del modelo.

### 5.1. Construcción de la Imagen de Entrenamiento
```bash
docker build -f DockerfileTrainPipeline . --tag flowguard-compose-retrain:v1
```

### 5.2. Ejecución del Pipeline
Ejecute el contenedor montando los volúmenes de código y datos. Reemplace las variables `<...>` con sus credenciales reales.

```bash
docker run --gpus all \
  -v $(pwd)/src/data:/app/data \
  -v $(pwd)/src/dataloader:/app/dataloader \
  -v $(pwd)/src/models:/app/models \
  -v $(pwd)/src/save:/app/save \
  -e AWS_ACCESS_KEY_ID=<AWS_KEY> \
  -e AWS_SECRET_ACCESS_KEY=<AWS_SECRET> \
  -e WANDB_KEY=<WANDB_KEY> \
  -e WANDB_RUN=false \
  -e MODEL=cognn \
  -e CLIENT='MCT_RETRAIN' \
  -e TASK=re-train \
  flowguard-compose-retrain:v1 --save /app/save/ --data /app/data/MCT_RETRAIN
```

**Qué sucede internamente:**
1.  Se descarga/genera el dataset más reciente.
2.  Se ejecuta `src/training_pipeline.py`.
3.  Si el nuevo modelo mejora al anterior, se actualiza en producción (carpeta `models`).

---

## 6. Operación: Inferencia

Existen dos modalidades para ejecutar la inferencia de anomalías.

### Opción A: Servicio API (Tiempo Real / On-Demand)
El servicio de inferencia ya se encuentra activo si ejecutó el `docker-compose`. Escucha en el puerto `5000`.

*   **Endpoint:** `POST http://localhost:5000/secure-trigger`
*   **Auth:** Basic Auth (admin:secret)

Si necesita ejecutarlo manualmente de forma aislada:
```bash
docker build -f DockerfileInferenceCPU . --tag flowguard-inference-cpu:v1
docker run -p 5000:5000 flowguard-inference-cpu:v1
```

### Opción B: Script ETL (Batch / Periódico)
Para procesar datos históricos o ejecutar inferencia programada sin pasar por la API HTTP, utilice el script ETL directo.

**Comando manual:**
```bash
MODEL='cognn' CLIENT='MCT' ROOT='http://localhost:9090' python3 src/dataloader/inference_ETL.py
```

**Ejecución en segundo plano (Background):**
```bash
nohup env MODEL="cognn" CLIENT="MCT" ROOT="http://localhost:9090" python3 src/dataloader/inference_ETL.py > output_log 2>&1 &
```

**Automatización (Cron):**
Para ejecutar cada minuto, añada a `crontab -e`:
```cron
* * * * * MODEL='cognn' CLIENT='MCT' ROOT='http://localhost:9090' /usr/bin/python3 /ruta/absoluta/a/src/dataloader/inference_ETL.py
```

---

## 8. Resumen de Acceso a Servicios

Una vez completado el despliegue e inicialización del cliente, los servicios están disponibles en las siguientes rutas con las credenciales por defecto:

| Servicio | URL | Usuario | Contraseña |
| :--- | :--- | :--- | :--- |
| **ThingsBoard** | [http://localhost:9090](http://localhost:9090) | `tenant@thingsboard.org` | `tenant` |
| **Node-RED** | [http://localhost:1880](http://localhost:1880) | `tenant` | `tenantairtrace` |
| **Inference API** | [http://localhost:5000](http://localhost:5000) | `admin` | `secret` |

> [!NOTE]
> Estas credenciales son las configuradas por defecto en `settings.js` y en la inicialización de ThingsBoard. Se recomienda cambiarlas para entornos de producción.
