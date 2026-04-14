
# FlowGuard - Guia de ThingsBoard

Guia de uso de ThingsBoard dentro del ecosistema FlowGuard para la gestion de dispositivos IoT, telemetria y deteccion de anomalias en sistemas de control industrial.

## Arquitectura

```
+------------------+       +------------------+       +---------------------+
|    Node-RED      |       |   ThingsBoard    |       |  Inference Service  |
|   (ETL Flows)    |<----->|   (IoT Platform) |<----->|  (CoGNN / STGNN)    |
|   Puerto: 1880   |       |   Puerto: 9090   |       |   Puerto: 5000      |
+------------------+       +--------+---------+       +---------------------+
                                    |
                           +--------+---------+
                           |   PostgreSQL     |
                           |   Puerto: 5432   |
                           +------------------+
```

Todos los servicios se comunican a traves de la red Docker `flowguard-compose_iot_network` (subnet `172.25.0.0/24`).

---

## Servicios Docker relacionados con ThingsBoard

### docker-compose.yml

| Servicio | Imagen | Puerto | IP Interna | Descripcion |
|---|---|---|---|---|
| `thingsboard` | `thingsboard/tb-postgres:4.1.0` | 9090, 1883, 7070, 5683-5688/udp | 172.25.0.2 | Plataforma IoT principal |
| `db` | `postgres:13` | 5432 | 172.25.0.23 | Base de datos de ThingsBoard |
| `nodered_tb` | `nodered/node-red:3.1.9` | 1880 | 172.25.0.3 | Orquestacion de flujos ETL |
| `inference-service` | `flowguard-stgnn-inference-cpu:v1` | 5000 | 172.25.0.4 | API de deteccion de anomalias |

### Variables de entorno de ThingsBoard

```yaml
environment:
  DATABASE_HOST: db
  DATABASE_PORT: 5433
  DATABASE_TYPE: postgresql
  DATABASE_NAME: thingsboard
  DATABASE_USER: tenant@thingsboard.org
  DATABASE_PASSWORD: tenant
```

### Volumenes

| Ruta local | Ruta contenedor | Descripcion |
|---|---|---|
| `./tb-data` | `/data` | Datos persistentes de ThingsBoard |
| `./tb-logs` | `/var/log/thingsboard` | Logs de ThingsBoard |
| `./postgres-data` | `/var/lib/postgresql/data` | Datos de PostgreSQL |

---

## Acceso a ThingsBoard

### Interfaz web

| URL | Contexto |
|---|---|
| `http://localhost:9090` | Desde la maquina host |
| `http://172.25.0.2:9090` | Desde la red Docker interna |

### Credenciales por defecto

| Rol | Usuario | Password |
|---|---|---|
| System Admin | `sysadmin@thingsboard.org` | `sysadmin` |
| Tenant Admin | `tenant@thingsboard.org` | `tenant` |

> Las credenciales del proyecto se almacenan en `deploy/ParametrosConfiguracion.txt`.

### Puertos disponibles

| Puerto | Protocolo | Uso |
|---|---|---|
| 9090 | HTTP | Interfaz web y API REST |
| 1883 | MQTT | Comunicacion de dispositivos via MQTT |
| 7070 | gRPC | Transporte Edge/gRPC |
| 5683-5688 | CoAP/UDP | Comunicacion de dispositivos via CoAP |

---

## API REST de ThingsBoard

El modulo `deploy/APIThingsboard.py` encapsula todas las llamadas a la API. Configuracion global:

```python
import APIThingsboard

# Autenticacion
credenciales = {"username": "tenant@thingsboard.org", "password": "tenant"}
token, refresh_token = APIThingsboard.extract_token(credenciales)
APIThingsboard.TOKEN = f'Bearer {token}'
APIThingsboard.Root = "http://localhost:9090"
```

### Endpoints principales

#### Autenticacion

```
POST /api/auth/login
Body: {"username": "...", "password": "..."}
Response: {"token": "...", "refreshToken": "..."}
```

#### Gestion de Clientes (Customers)

```python
# Crear o verificar existencia de un cliente
customer_id, status = APIThingsboard.clienteIDStatus("ESAMUR")
# status: "New" (recien creado) o "Old" (ya existia)
```

```
POST /api/customer
Body: {"title": "ESAMUR"}
```

#### Creacion de Dispositivos en masa

```python
import pandas as pd

# CSV debe tener columnas: name, type
df_devices = pd.read_csv('deploy/ESAMUR/DeviceImport.csv')
df_devices = APIThingsboard.crear_devicesBulk(df_devices)
# Resultado: DataFrame con columnas adicionales devicesId y accessToken
```

Los tokens de acceso generados se guardan en `deploy/{Cliente}/DeviceimportCredentials_{Cliente}.csv`.

#### Rule Chains

```python
rule_chain_id = APIThingsboard.extraer_DevicesRuleChainId("ESAMUR", "Device")
```

Las plantillas JSON se encuentran en `deploy/Plantillas/DeviceRuleChains/`:
- `default_root_rule_chain.json`
- `devices_root_rule_chain.json`
- `buckets_root_rule_chain.json`
- `models_root_rule_chain.json`
- `estimaciones_root_rule_chain.json`
- `raw_root_rule_chain.json`
- `matriz_root_rule_chain.json`

#### Device Profiles

```python
profile_id = APIThingsboard.extraer_DevicesProfile("ESAMUR", "Buckets")
```

Las plantillas JSON estan en `deploy/Plantillas/DeviceProfiles/`:
- `profile_default.json`
- `profile_device.json`
- `profile_buckets.json`
- `profile_models.json`
- `profile_estimaciones_modelo.json`
- `profile_raw.json`
- `profile_control.json`
- `profile_matriz_relacion.json`

---

## Tipos de dispositivos

El sistema crea automaticamente los siguientes tipos de dispositivos por cada cliente:

| Tipo | Descripcion |
|---|---|
| `{Cliente} Device` | Sensores fisicos del sistema industrial |
| `{Cliente} Buckets` | Agregaciones estadisticas (Media/Mediana, ventanas de 1, 5, 10 seg) |
| `{Cliente} Models` | Un dispositivo por modelo (M1, M2, M3) |
| `{Cliente} Estimaciones Modelo` | Estimaciones absolutas del modelo |
| `{Cliente} Estimaciones relativo Modelo` | Estimaciones relativas del modelo |
| `{Cliente} Matriz Relacion` | Matrices de relacion entre sensores |
| `{Cliente} Niveles Modelos` | Niveles de criticidad por modelo |
| `{Cliente} RAW` | Datos crudos sin procesar |
| `{Cliente} Control` | Dispositivos de control |
| `CLIENTES Niveles de Criticidad` | Bucket global de niveles de criticidad |

---

## Envio de telemetria

### Via MQTT (puerto 1883)

```sh
mosquitto_pub -h localhost -p 1883 -t "v1/devices/me/telemetry" \
  -u "<ACCESS_TOKEN>" \
  -m '{"temperatura": 25.5, "presion": 1.2}'
```

### Via HTTP API

```sh
curl -X POST http://localhost:9090/api/v1/<ACCESS_TOKEN>/telemetry \
  -H "Content-Type: application/json" \
  -d '{"temperatura": 25.5, "presion": 1.2}'
```

### Via API REST autenticada

```sh
# Obtener token
TOKEN=$(curl -s -X POST http://localhost:9090/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"tenant@thingsboard.org","password":"tenant"}' | jq -r .token)

# Enviar telemetria a un dispositivo por su ID
curl -X POST "http://localhost:9090/api/plugins/telemetry/DEVICE/<DEVICE_ID>/timeseries/ANY" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"temperatura": 25.5}'
```

Los `ACCESS_TOKEN` se generan automaticamente al crear dispositivos y se almacenan en los archivos `DeviceimportCredentials_*.csv`.

---

## Configuracion del entorno del cliente

### Prerequisitos

1. Editar `deploy/Client.json` con el cliente y modelo:

```json
{
  "Client": "ESAMUR",
  "Model": "M3"
}
```

2. Verificar credenciales en `deploy/ParametrosConfiguracion.txt`.

3. Preparar el CSV de dispositivos en `deploy/{Cliente}/DeviceImport.csv` (columnas: `name`, `type`).

### Opcion 1: Scripts individuales

```sh
# 1. Configuracion general: crea buckets base y flujos de niveles de criticidad en Node-RED
python3 deploy/1_Configuracion_General.py

# 2. Subir niveles de criticidad iniciales a ThingsBoard
python3 deploy/1.1_Subir_Niveles_Criticidad_Inicial_Bulk.py

# 3. Crear entorno completo del cliente (customers, devices, profiles, rule chains)
python3 deploy/2_Crear_Entorno_Cliente_ThingsBoard.py

# 4. Crear flujos ETL en Node-RED para el cliente
python3 deploy/2.2_Crear_ETL_NodeRed_Cliente.py
```

### Opcion 2: Script unificado

```sh
python3 deploy/env_client.py
```

### Opcion 3: Contenedor Docker

```sh
docker build -f DockerfileEnvClient . --tag flowguard-env-client:v1
docker run --rm --network flowguard-compose_iot_network flowguard-env-client:v1
```

> **Nota:** Si se ejecutan los scripts desde dentro de un contenedor Docker, las funciones `crear_flow_nodered` y `update_flow_nodered` deben llamarse sin el parametro TOKEN (usar autenticacion basica en su lugar).

---

## Node-RED y ThingsBoard

### Acceso a Node-RED

| URL | Contexto |
|---|---|
| `http://localhost:1880` | Desde la maquina host |
| `http://172.25.0.3:1880` | Desde la red Docker interna |

### Credenciales de Node-RED

Definidas en `deploy/ParametrosConfiguracion.txt`:
- **Usuario:** `tenant`
- **Password:** configurado en el archivo

### Flujos desplegados

| Flujo | Descripcion |
|---|---|
| **Critical Level** | Gestion de niveles de criticidad entre ThingsBoard y el sistema |
| **ETL Flows** | Extraccion, transformacion y carga de datos del cliente |
| **PrevioRawFlow** | Preprocesamiento de datos crudos |

Los flujos se configuran automaticamente desde las plantillas en `deploy/Plantillas/ETLNodeRed/`.

---

## Gestion de niveles de criticidad

### Consultar niveles actuales

```sh
python3 deploy/3_Solicitar_Niveles_Criticidad.py
```

### Modificar un nivel

```sh
MODEL='M3' LEVEL=<NIVEL> VALUE=<VALOR> python3 deploy/3.1_Modificar_Niveles_Criticidad.py
```

### Subir thresholds

```sh
python3 deploy/4_Subir_thresholds.py
```

Los niveles de criticidad se almacenan por cliente en `deploy/{Cliente}/Niveles de Criticidad.csv`.

---

## Integracion con el servicio de inferencia

El servicio de inferencia se conecta a ThingsBoard para:

1. **Leer telemetria** de los dispositivos del cliente
2. **Ejecutar el modelo** CoGNN/STGNN sobre los datos
3. **Escribir resultados** (scores de anomalia, estimaciones) de vuelta a ThingsBoard

### Variables de entorno del servicio

| Variable | Valor | Descripcion |
|---|---|---|
| `MODEL` | `cognn` | Modelo a usar (`cognn`, `stgnn-gat`) |
| `CLIENT` | `ESAMUR` | Nombre del cliente |
| `ROOT` | `http://172.25.0.2:9090` | URL interna de ThingsBoard |
| `TASK` | `inference` | Tarea a ejecutar |

### Ejecutar inferencia periodica (fuera de Docker)

```sh
MODEL='cognn' CLIENT='ESAMUR' ROOT='http://localhost:9090' python3 src/dataloader/inference_ETL.py
```

En background:

```sh
nohup env MODEL="cognn" CLIENT="ESAMUR" ROOT="http://localhost:9090" \
  python3 src/dataloader/inference_ETL.py > output_log 2>&1 &
```

---

## Clientes soportados

| Cliente | Descripcion | Directorio |
|---|---|---|
| ESAMUR | Planta de tratamiento de aguas (Murcia) | `deploy/ESAMUR/` |
| MCT | Sistema de control industrial | `deploy/MCT/` |
| WADI | Sistema de distribucion de agua | Datasets en `src/models/` |
| SWAT | Tratamiento seguro de agua | Datasets en `src/models/` |

Cada cliente tiene en su directorio:
- `DeviceImport.csv` - Dispositivos a crear en ThingsBoard
- `DeviceimportCredentials_{Cliente}.csv` - Credenciales generadas
- `OthersimportCredentials_{Cliente}.csv` - Credenciales de dispositivos auxiliares
- `DeviceimportCredentials_CORE.csv` - Credenciales de dispositivos base
- `Niveles de Criticidad.csv` - Umbrales de alerta

---

## Troubleshooting

| Problema | Solucion |
|---|---|
| Error de permisos en `tb-data/` | `sudo chmod -R 777 tb-data` |
| Error en `tb-data/db` | `sudo chmod 750 tb-data/db` |
| ThingsBoard no arranca | Verificar PostgreSQL: `docker logs postgres-db` |
| Error de red entre servicios | Verificar red: `docker network ls \| grep flowguard` |
| Error enviando flujos a Node-RED desde contenedor | Usar autenticacion basica (sin TOKEN) |
| Inference no conecta a ThingsBoard | Verificar `ROOT=http://172.25.0.2:9090` |
| Token expirado | Re-ejecutar `extract_token()` para obtener nuevo token |
| Dispositivo sin telemetria | Verificar `accessToken` en CSV y endpoint MQTT/HTTP |
