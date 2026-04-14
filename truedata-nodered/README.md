
# FlowGuard - Guia de Node-RED

Guia de uso de Node-RED dentro del ecosistema FlowGuard para la orquestacion de flujos ETL, agregacion de datos de sensores y comunicacion con ThingsBoard.

## Arquitectura

```
                          +------------------+
                          |    Node-RED      |
                          |   Puerto: 1880   |
                          |  IP: 172.25.0.3  |
                          +--------+---------+
                                   |
              +--------------------+--------------------+
              |                    |                     |
   +----------v--------+ +--------v---------+ +--------v-----------+
   |   ThingsBoard     | | Inference Service| | Sensores / APIs    |
   | HTTP API (9090)   | | HTTP API (5000)  | | (fuentes externas) |
   | MQTT (1883)       | |                  | |                    |
   +-------------------+ +------------------+ +--------------------+
```

Node-RED actua como middleware ETL entre las fuentes de datos (sensores, APIs externas) y ThingsBoard, procesando, transformando y enrutando telemetria en tiempo real.

---

## Servicio Docker

### Configuracion en docker-compose.yml

```yaml
nodered_tb:
  restart: always
  image: nodered/node-red:3.1.9
  ports:
    - "1880:1880"
  volumes:
    - ./data:/data
    - ./settings.js:/data/settings.js:ro
  environment:
    - TZ=Europe/Madrid
  networks:
    iot_network:
      ipv4_address: 172.25.0.3
  user: "0:0"
```

| Parametro | Valor | Descripcion |
|---|---|---|
| **Imagen** | `nodered/node-red:3.1.9` | Version fija de Node-RED |
| **Puerto** | 1880 | Editor web y endpoints HTTP |
| **IP interna** | 172.25.0.3 | IP fija en la red Docker |
| **Volumen** | `./data:/data` | Persistencia de flujos, credenciales y configuracion |
| **Volumen** | `./settings.js:/data/settings.js:ro` | Configuracion del runtime (solo lectura) |
| **Timezone** | `Europe/Madrid` | Zona horaria para timestamps |
| **Usuario** | `0:0` (root) | Necesario para permisos de escritura en el volumen |

### Red Docker

```
Red: flowguard-compose_iot_network (172.25.0.0/24)

Node-RED (172.25.0.3) ---HTTP---> ThingsBoard (172.25.0.2:9090)
Node-RED (172.25.0.3) ---HTTP---> Inference Service (172.25.0.4:5000)
```

La red debe crearse antes de levantar los servicios:

```sh
docker network create --driver=bridge --subnet=172.25.0.0/24 flowguard-compose_iot_network
```

---

## Acceso a Node-RED

### URLs

| URL | Contexto |
|---|---|
| `http://localhost:1880` | Desde la maquina host |
| `http://172.25.0.3:1880` | Desde otros contenedores en la red Docker |

### Credenciales

| Campo | Valor |
|---|---|
| **Usuario** | `tenant` |
| **Password** | `tenantairtrace` (hash bcrypt en settings.js) |
| **Metodo** | adminAuth (formulario de login en el editor) |

Las credenciales se definen en dos lugares:
- **`settings.js`** - Configuracion del editor Node-RED (adminAuth con bcrypt)
- **`deploy/ParametrosConfiguracion.txt`** - Credenciales en texto plano para scripts de deploy

---

## Configuracion: settings.js

El archivo `settings.js` se monta automaticamente en el contenedor via `./settings.js:/data/settings.js:ro`. Configuraciones clave:

### Seguridad (adminAuth)

```javascript
adminAuth: {
    type: "credentials",
    users: [{
        username: "tenant",
        password: "$2b$08$yEVqU87BxV5xTzwb9yokb.eEW0OKyWuUiyFBAfaC/DfPDCakgCINm",
        permissions: "*"
    }]
}
```

- `permissions: "*"` otorga acceso completo (lectura + escritura)
- El password es un hash bcrypt. Para generar uno nuevo:

```sh
node -e "console.log(require('bcryptjs').hashSync('tu_password', 8))"
```

### Cifrado de credenciales

```javascript
credentialSecret: "airtrace"
```

Este secreto cifra las credenciales almacenadas en los nodos (passwords de MQTT, HTTP auth, etc.). **No cambiar una vez configurado**, o se perderan las credenciales existentes.

### Archivo de flujos

```javascript
flowFile: 'flows.json'
```

Los flujos se almacenan en `data/flows.json` y las credenciales cifradas en `data/flows_cred.json`.

### Otras configuraciones relevantes

| Propiedad | Valor | Descripcion |
|---|---|---|
| `uiPort` | 1880 | Puerto del servidor web |
| `flowFilePretty` | true | JSON formateado (mejor para version control) |
| `functionExternalModules` | true | Permite `require()` en nodos Function |
| `functionTimeout` | 0 | Sin timeout para funciones (0 = ilimitado) |
| `mqttReconnectTime` | 15000 | Reintento MQTT cada 15 segundos |
| `serialReconnectTime` | 15000 | Reintento serie cada 15 segundos |
| `debugMaxLength` | 1000 | Max caracteres en debug sidebar |
| `diagnostics.enabled` | true | Endpoint `/diagnostics` habilitado |
| `runtimeState.enabled` | false | Control start/stop de flujos deshabilitado |
| `logging.console.level` | "info" | Nivel de log |

---

## API REST de Node-RED

Node-RED expone una API REST para gestionar flujos programaticamente. Los scripts de deploy del proyecto la utilizan extensivamente.

### Autenticacion

**Via Token (Bearer):**

```python
def extract_token_nodered(credenciales):
    credenciales["client_id"] = "node-red-admin"
    credenciales["grant_type"] = "password"
    credenciales["scope"] = "*"

    endpoint = "http://localhost:1880/auth/token"
    response = requests.post(endpoint, json=credenciales)
    return response.json().get('access_token')
```

```sh
# Obtener token
curl -X POST http://localhost:1880/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "node-red-admin",
    "grant_type": "password",
    "scope": "*",
    "username": "tenant",
    "password": "tenantairtrace"
  }'
# Response: {"access_token": "...", "expires_in": 604800, "token_type": "Bearer"}
```

**Via Basic Auth:**

```sh
curl -u tenant:tenantairtrace http://localhost:1880/flows
```

> **Nota:** Desde contenedores Docker, usar Basic Auth (sin token). Desde el host, se puede usar Bearer token.

### Endpoints principales

| Metodo | Endpoint | Descripcion |
|---|---|---|
| `GET` | `/flows` | Obtener todos los flujos (tabs + nodos) |
| `POST` | `/flows` | Reemplazar todos los flujos (deploy completo) |
| `POST` | `/flow` | Crear un flujo nuevo (tab con nodos) |
| `GET` | `/flow/:id` | Obtener un flujo por ID |
| `PUT` | `/flow/:id` | Actualizar un flujo existente |
| `DELETE` | `/flow/:id` | Eliminar un flujo |
| `GET` | `/nodes` | Listar nodos instalados |
| `POST` | `/nodes` | Instalar un nuevo nodo |
| `GET` | `/settings` | Obtener configuracion del runtime |
| `GET` | `/diagnostics` | Informacion de diagnostico |
| `POST` | `/auth/token` | Obtener token de autenticacion |
| `POST` | `/auth/revoke` | Revocar token |

### Crear un flujo

```python
flow = {
    "id": "mi_flujo_id",
    "label": "Mi Flujo ETL",
    "nodes": [...],  # Lista de nodos JSON
    "configs": []
}

response = requests.post(
    "http://localhost:1880/flow",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json=flow
)
```

### Actualizar flujos existentes

El proyecto usa una estrategia de merge: obtiene los flujos actuales, actualiza nodos existentes por ID, y agrega nodos nuevos:

```python
# 1. Obtener flujos actuales
flows_actuales = requests.get("http://localhost:1880/flows", auth=(...)).json()

# 2. Buscar la tab correcta
for tab in flows_actuales:
    if tab.get("type") == "tab" and tab.get("label") == "Mi Flujo":
        flow_z = tab["id"]

# 3. Merge: actualizar existentes, agregar nuevos
for nodo_local in mis_nodos:
    encontrado = False
    for nodo_actual in flows_actuales:
        if nodo_actual.get("id") == nodo_local.get("id"):
            nodo_actual.update({k: v for k, v in nodo_local.items() if k != "z"})
            encontrado = True
    if not encontrado:
        nodo_local["z"] = flow_z
        flows_actuales.append(nodo_local)

# 4. Deploy completo
requests.post("http://localhost:1880/flows", auth=(...), json=flows_actuales)
```

---

## Flujos desplegados en FlowGuard

### 1. Critical Level (Niveles de Criticidad)

- **ID:** `Critical Level`
- **Label:** `Critical Level`
- **Script:** `deploy/1_Configuracion_General.py`
- **Template:** `deploy/Plantillas/ETLNodeRed/flows Critical Levels.json`

**Funcion:** Gestiona los niveles de criticidad entre ThingsBoard y el sistema de inferencia.

**Flujo de datos:**
```
POST /endpoint/NivelesCriticidad
    |
    v
[HTTP Response 200] --> [Procesamiento] --> [HTTP Load a ThingsBoard]
```

**Nodos principales:**
- `http in` - Endpoint `POST /endpoint/NivelesCriticidad`
- `http response` - Respuesta 200 inmediata
- `function` - Procesamiento y transformacion de datos
- `http request` - Carga a ThingsBoard via API telemetria

**Placeholders reemplazados:**
| Placeholder | Valor real |
|---|---|
| `ROOT_ThingsBoard` | `http://172.25.0.2:9090` |
| `accessTokenClientesNiveles` | Token del bucket "CLIENTES Niveles de Criticidad" |
| `deviceIdClientesNiveles` | ID del dispositivo de niveles |
| `deviceIdNivelesDescartes` | ID del bucket de descartes |
| `UsernameThingsBoard` | `tenant@thingsboard.org` |
| `PasswordThingsBoard` | `tenant` |

### 2. Data Preparation Stage (ETL del Cliente)

- **ID:** `{Cliente}ETL` (ej: `ESAMURETL`)
- **Label:** `Data preparation Stage {Cliente}`
- **Script:** `deploy/2.2_Crear_ETL_NodeRed_Cliente.py`
- **Template:** `deploy/Plantillas/ETLNodeRed/ETLflows.json`

**Funcion:** Pipeline ETL completo para un cliente. Recibe datos de sensores, los transforma y los carga en ThingsBoard como agregaciones estadisticas.

**Flujo de datos:**
```
POST /endpoint/agregar{Cliente}
    |
    v
[HTTP Response 200]
    |
    v
[ToNumber] --> Convierte boolean/string a numerico (0/1)
    |
    +---> [Agregacion Media 1s]   ---> HTTP Load --> ThingsBoard (IDMEDIA1ID)
    +---> [Agregacion Media 5s]   ---> HTTP Load --> ThingsBoard (IDMEDIA5ID)
    +---> [Agregacion Media 10s]  ---> HTTP Load --> ThingsBoard (IDMEDIA10ID)
    +---> [Agregacion Mediana 1s] ---> HTTP Load --> ThingsBoard (IDMEDIANA1ID)
    +---> [Agregacion Mediana 5s] ---> HTTP Load --> ThingsBoard (IDMEDIANA5ID)
    +---> [Agregacion Mediana 10s]--> HTTP Load --> ThingsBoard (IDMEDIANA10ID)
```

**Nodos principales:**
- `http in` - Endpoint `POST /endpoint/agregar{Cliente}`
- `http response` - Respuesta 200 inmediata
- `function` (ToNumber) - Normaliza valores: `true/active -> 1`, `false/inactive -> 0`
- `function` (Agregacion) - Calcula media/mediana por ventanas de tiempo
- `http request` (HTTP Load) - POST a ThingsBoard telemetry API con access tokens

**Placeholders reemplazados:**
| Placeholder | Valor real |
|---|---|
| `XXXXXXXXXX` | Nombre del cliente (ej: `ESAMUR`) |
| `ROOT_ThingsBoard` | `http://172.25.0.2:9090` |
| `YYYYYYYYYY` | Lista de dispositivos formateada como JSON array |
| `IDMEDIA1ID` | Access token del bucket Media Ventana 1seg |
| `IDMEDIA5ID` | Access token del bucket Media Ventana 5seg |
| `IDMEDIA10ID` | Access token del bucket Media Ventana 10seg |
| `IDMEDIANA1ID` | Access token del bucket Mediana Ventana 1seg |
| `IDMEDIANA5ID` | Access token del bucket Mediana Ventana 5seg |
| `IDMEDIANA10ID` | Access token del bucket Mediana Ventana 10seg |

### 3. RAW Data (Datos crudos previos)

- **ID:** `PrevioRaw{Cliente}` (ej: `PrevioRawESAMUR`)
- **Label:** `RAW Data {Cliente}`
- **Script:** `deploy/2.2_Crear_ETL_NodeRed_Cliente.py`
- **Template:** `deploy/Plantillas/ETLNodeRed/PrevioRawFlow.json`

**Funcion:** Preprocesa datos crudos de sensores antes de entrar al pipeline ETL principal.

**Flujo de datos:**
```
POST /endpoint/previo{Cliente}
    |
    v
[HTTP Response 200]
    |
    v
[Procesado y Preparacion]
    |  - Reemplaza parentesis por corchetes
    |  - Reemplaza comillas simples por dobles
    |  - Convierte None/True/False de Python a null/true/false de JSON
    |
    v
[Split] --> [Iteracion por registro] --> [HTTP Load a ThingsBoard]
```

**Placeholders reemplazados:**
| Placeholder | Valor real |
|---|---|
| `XXXXXXXXXX` | Nombre del cliente |
| `ROOT_ThingsBoard` | `http://172.25.0.2:9090` |
| `UsernameThingsBoard` | `tenant@thingsboard.org` |
| `PasswordThingsBoard` | `tenant` |
| `TOKEN_CONTROL` | Access token del dispositivo `{Cliente} Control` |

---

## Tipos de nodos utilizados

| Tipo de nodo | Uso en FlowGuard |
|---|---|
| `http in` | Endpoints HTTP que reciben datos de sensores y ETL |
| `http response` | Respuesta inmediata 200 al emisor |
| `http request` | Llamadas HTTP a ThingsBoard (POST telemetria) |
| `function` | Logica de negocio: transformacion de datos, agregaciones, conversion de tipos |
| `debug` | Depuracion de mensajes en la sidebar |
| `split` | Division de arrays en mensajes individuales |
| `change` | Modificacion de propiedades del mensaje |
| `switch` | Enrutamiento condicional de mensajes |

---

## Despliegue de flujos

### Opcion 1: Scripts automatizados

**Configuracion general (Critical Levels + buckets base):**

```sh
python3 deploy/1_Configuracion_General.py
```

**Flujos ETL del cliente:**

```sh
python3 deploy/2.2_Crear_ETL_NodeRed_Cliente.py
```

**Todo junto:**

```sh
python3 deploy/env_client.py
```

### Opcion 2: Manual via editor web

1. Abrir `http://localhost:1880`
2. Login con `tenant` / `tenantairtrace`
3. Importar flujos: Menu hamburguesa -> Import -> Pegar JSON
4. Click "Deploy" para activar

### Opcion 3: Via API REST

```sh
# Obtener token
TOKEN=$(curl -s -X POST http://localhost:1880/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"node-red-admin","grant_type":"password","scope":"*","username":"tenant","password":"tenantairtrace"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Crear flujo
curl -X POST http://localhost:1880/flow \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test_flow",
    "label": "Test Flow",
    "nodes": [],
    "configs": []
  }'
```

---

## Integracion Node-RED <-> ThingsBoard

### Patron de comunicacion

```
Sensor/API --> POST /endpoint/{flujo} --> Node-RED --> POST /api/v1/{TOKEN}/telemetry --> ThingsBoard
```

1. Los datos llegan a Node-RED via endpoints HTTP definidos en nodos `http in`
2. Node-RED transforma los datos (conversion de tipos, agregacion, formateo)
3. Node-RED envia los datos procesados a ThingsBoard via HTTP API usando los access tokens de los dispositivos

### URLs de ThingsBoard desde Node-RED

Dentro de la red Docker, Node-RED accede a ThingsBoard en:
- **API REST:** `http://172.25.0.2:9090/api/v1/{ACCESS_TOKEN}/telemetry`
- **Login:** `http://172.25.0.2:9090/api/auth/login`

### Dispositivos de agregacion

Node-RED escribe en estos dispositivos de ThingsBoard:

| Dispositivo | Access Token Placeholder | Descripcion |
|---|---|---|
| `{Cliente} Aggregation Media Ventana 1seg` | `IDMEDIA1ID` | Media movil, ventana 1 segundo |
| `{Cliente} Aggregation Media Ventana 5seg` | `IDMEDIA5ID` | Media movil, ventana 5 segundos |
| `{Cliente} Aggregation Media Ventana 10seg` | `IDMEDIA10ID` | Media movil, ventana 10 segundos |
| `{Cliente} Aggregation Mediana Ventana 1seg` | `IDMEDIANA1ID` | Mediana movil, ventana 1 segundo |
| `{Cliente} Aggregation Mediana Ventana 5seg` | `IDMEDIANA5ID` | Mediana movil, ventana 5 segundos |
| `{Cliente} Aggregation Mediana Ventana 10seg` | `IDMEDIANA10ID` | Mediana movil, ventana 10 segundos |

Los access tokens se obtienen automaticamente de `deploy/{Cliente}/OthersimportCredentials_{Cliente}.csv`.

---

## Plantillas de flujos

Las plantillas JSON se encuentran en `deploy/Plantillas/ETLNodeRed/`:

| Archivo | Flujo | Descripcion |
|---|---|---|
| `ETLflows.json` | Data preparation Stage | Pipeline ETL principal con agregaciones |
| `PrevioRawFlow.json` | RAW Data | Preprocesamiento de datos crudos |
| `flows Critical Levels.json` | Critical Level | Gestion de niveles de criticidad (version actual) |
| `flows Critical Levels2.json` | - | Version alternativa de niveles de criticidad |
| `flows Critical Levels old.json` | - | Version antigua (backup) |

### Sistema de placeholders

Las plantillas usan marcadores que se reemplazan programaticamente:

```python
# Ejemplo de reemplazo en 2.2_Crear_ETL_NodeRed_Cliente.py
ETLFlow = ETLFlow.replace("ROOT_ThingsBoard", "http://172.25.0.2:9090")
ETLFlow = ETLFlow.replace("XXXXXXXXXX", "ESAMUR")
ETLFlow = ETLFlow.replace("IDMEDIA1ID", access_token_media_1)
```

Los IDs de nodos tambien usan el placeholder `XXXXXXXXXX` como prefijo, lo que genera IDs unicos por cliente (ej: `ESAMUR1e1eff9f77177413`).

---

## Estructura de un flujo Node-RED

```json
{
  "id": "ESAMURETL",
  "label": "Data preparation Stage ESAMUR",
  "nodes": [
    {
      "id": "nodo_unico_id",
      "type": "http in",
      "name": "Endpoint",
      "url": "/endpoint/agregarESAMUR",
      "method": "post",
      "x": 180,
      "y": 260,
      "z": "ESAMURETL",
      "wires": [["siguiente_nodo_id"]]
    }
  ],
  "configs": []
}
```

| Campo | Descripcion |
|---|---|
| `id` | Identificador unico del flujo (tab) |
| `label` | Nombre visible en la pestana |
| `nodes` | Array de nodos con su configuracion |
| `nodes[].id` | ID unico del nodo |
| `nodes[].type` | Tipo de nodo (`http in`, `function`, `http request`, etc.) |
| `nodes[].z` | ID del flujo (tab) al que pertenece |
| `nodes[].wires` | Conexiones de salida a otros nodos |
| `nodes[].x`, `nodes[].y` | Posicion en el canvas del editor |
| `configs` | Nodos de configuracion compartidos |

---

## Backup y restauracion

### Backup manual

Los datos de Node-RED se persisten en `./data/`:

```sh
# Backup
tar czf nodered_backup_$(date +%Y%m%d).tar.gz data/

# Restaurar
tar xzf nodered_backup_XXXXXXXX.tar.gz
```

### Archivos importantes en data/

| Archivo | Descripcion |
|---|---|
| `flows.json` | Todos los flujos y nodos |
| `flows_cred.json` | Credenciales cifradas de los nodos |
| `settings.js` | Configuracion del runtime |
| `package.json` | Dependencias y nodos adicionales instalados |
| `.config.nodes.json` | Cache de nodos instalados |

### Backup via API

```sh
# Exportar todos los flujos
curl -u tenant:tenantairtrace http://localhost:1880/flows > flows_backup.json

# Restaurar flujos
curl -X POST -u tenant:tenantairtrace \
  -H "Content-Type: application/json" \
  -d @flows_backup.json \
  http://localhost:1880/flows
```

---

## Instalar nodos adicionales

### Via editor web

1. Menu hamburguesa -> Manage palette
2. Tab "Install"
3. Buscar el nodo deseado
4. Click "Install"

### Via npm en el contenedor

```sh
docker exec -it <container_id> bash
cd /data
npm install node-red-contrib-<nombre-nodo>
```

### Via package.json

Agregar la dependencia en `data/package.json` y reiniciar el contenedor.

---

## Troubleshooting

| Problema | Solucion |
|---|---|
| No se puede acceder al editor | Verificar que el contenedor esta corriendo: `docker ps \| grep nodered` |
| Error de permisos en `data/` | El contenedor corre como root (`user: "0:0"`). Verificar permisos del host |
| Credenciales perdidas tras cambiar settings.js | No cambiar `credentialSecret` despues de la primera configuracion |
| Error "token" al crear flujos desde contenedor | Usar autenticacion basica (sin Bearer token) |
| Flujos no se despliegan | Verificar credenciales en `ParametrosConfiguracion.txt` |
| HTTP Load falla a ThingsBoard | Verificar que la URL usa `172.25.0.2:9090` (no localhost) desde Node-RED |
| Nodo function con error | Verificar que `functionExternalModules: true` en settings.js |
| MQTT no reconecta | `mqttReconnectTime` esta en 15000ms (15 seg). Verificar que ThingsBoard esta activo |
| Cambios en settings.js no aplican | El archivo se monta como volumen, solo reiniciar: `docker compose restart nodered_tb` |
