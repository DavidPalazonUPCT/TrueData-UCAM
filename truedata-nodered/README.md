# Node-RED — pipeline v2

Node-RED es el pre-procesador y router del pipeline v2: recibe el scan
bulk del OPC Client vía HTTP, publica telemetría a ThingsBoard por
Gateway MQTT API, y dispara la inferencia ML en paralelo.

- **Imagen:** `nodered/node-red:3.1.9`
- **Puerto:** `1880` (editor + endpoints HTTP)
- **Contratos de API:** ver
  [`docs/contracts/opc-ingest.md`](../docs/contracts/opc-ingest.md) y
  [`docs/contracts/ml-inference.md`](../docs/contracts/ml-inference.md).
- **Setup end-to-end:** ver [`docs/SETUP.md`](../docs/SETUP.md) (guía
  cross-service: red Docker, Gateway en ThingsBoard, token en Node-RED,
  validación).

---

## Qué expone

| Endpoint | Método | Descripción | Contrato |
|---|---|---|---|
| `/api/opc-ingest` | POST | Ingesta de scan bulk del OPC Client | [opc-ingest.md](../docs/contracts/opc-ingest.md) |
| `/admin/set-ml-url` | POST | **Dev only** — setea URL de ML inference en runtime | — |
| `/admin/clear-ml-url` | POST | **Dev only** — limpia URL de ML inference | — |
| `/admin/get-ml-url` | GET | **Dev only** — lee URL actual | — |
| `/` | GET | Editor Node-RED (UI) | — |

Los endpoints `/admin/*` responden `404` byte-identical a un path
inexistente salvo que `NR_ADMIN_ENABLED=true` esté en el entorno del
contenedor. En producción esta variable NO debe setearse.

---

## Arrancar

La red Docker externa debe existir previamente (una sola vez):

```sh
docker network create truedata_iot_network
```

Desde este directorio:

```sh
docker compose up -d
```

O desde la raíz del repo, levanta también ThingsBoard:

```sh
docker compose up -d
```

El `flows.json` y `settings.js` se montan como bind mount desde este
directorio, por lo que el flow `OPC Ingest v2` se carga automáticamente
al arrancar.

### Configuración del broker MQTT

El flow contiene un config node `TB Gateway` que conecta a
`thingsboard:1883`. **Las credenciales no se commitean** (encriptadas
con un `credentialSecret` por instancia). Hay que setear manualmente el
access token del Gateway device de TB en la UI:

1. Login en `http://localhost:1880` (ver credenciales abajo).
2. Editar el config node `TB Gateway` → tab Security → `user =
   <GATEWAY_TOKEN>` → Update → Deploy.

El `GATEWAY_TOKEN` se genera al crear el Gateway device en TB. Ver
[`docs/SETUP.md`](../docs/SETUP.md) para el procedimiento completo.

---

## Health check

```sh
# 1. UI responde
curl -sI http://localhost:1880 | head -1
# Esperado: HTTP/1.1 200 OK

# 2. Endpoint de ingesta acepta un scan mínimo
curl -s -X POST http://localhost:1880/api/opc-ingest \
  -H "Content-Type: application/json" \
  -d "{\"ts\": $(date +%s%3N), \"values\": {\"HEALTHCHECK\": 1}}"
# Esperado: {"status":"ok","tags":1}

# 3. Desde un container de la misma red: DNS + TCP a TB
docker exec truedata-nodered_tb-1 nc -zv thingsboard 1883
# Esperado: Connection to thingsboard 1883 port [tcp/*] succeeded!
```

---

## Credenciales (dev)

| Campo | Valor |
|---|---|
| URL editor | `http://localhost:1880` |
| Usuario | `tenant` |
| Password | hash bcrypt en `settings.js` (no recuperable desde el hash; si se pierde, regenerar con `node -e "console.log(require('bcryptjs').hashSync('tu_password', 8))"` y reescribir `settings.js`) |
| `credentialSecret` | definido en `settings.js` (no cambiar post-deploy; invalida credentials cifradas) |

---

## Estructura del flow actual (`OPC Ingest v2`)

```
[http-in /api/opc-ingest]
         │
         ▼
[function: validate + connects + telemetry + ml + ack]
         │
         ├──► Salida 1 → [mqtt-out → v1/gateway/telemetry (+ connect)]
         │
         ├──► Salida 2 → [http-request → ML inference API]
         │
         └──► Salida 3 → [http-response 200/400]
```

El function node vive embebido en `data/flows.json`. Pasos internos:

1. **Validación:** `ts` debe ser `typeof "number"`; `values` debe ser
   objeto no vacío. Si no, sale por la salida 3 con `400`.
2. **Connect lazy:** para cada tag que NR no ha visto antes en este
   runtime, publica un `v1/gateway/connect` con
   `{device: <tag>, type: <DEVICE_PROFILE>}`. TB auto-crea el device
   con el profile indicado. La lista de devices ya vistos se cachea en
   `flow.connectedDevices` (memoria; se vacía en restart).
3. **Telemetry:** publica `v1/gateway/telemetry` con
   `{<tag>: [{ts, values: {value}}]}` para todos los tags del scan, con
   el mismo `ts` client-side.
4. **ML paralelo:** si `flow.ML_INFERENCE_URL` está set, postea
   `{ts, sensors: values}` con timeout 5 s (fire-and-forget).
5. **Ack:** responde `{status: "ok", tags: N}` al cliente OPC.

---

## Variables de entorno y de flow

| Fuente | Variable | Default | Descripción |
|---|---|---|---|
| `docker-compose.yml` (env) | `TZ` | `Europe/Madrid` | Zona horaria |
| `docker-compose.yml` (env) | `NR_ADMIN_ENABLED` | unset | Si `true`, expone `/admin/*` (solo dev) |
| Flow context | `ML_INFERENCE_URL` | unset | URL del servicio ML. Si unset, salida 2 silenciada |
| Flow context | `DEVICE_PROFILE` | `sensor_planta` | Profile TB con el que NR auto-provisiona devices |
| Flow context | `connectedDevices` | `{}` | Cache en memoria de devices ya conectados (se vacía en restart) |

---

## Troubleshooting

| Problema | Causa probable / mitigación |
|---|---|
| `POST /api/opc-ingest` devuelve `400 ts missing or not number` | El body debe llevar `ts` como número Unix ms. Ver [contracts/opc-ingest.md](../docs/contracts/opc-ingest.md) |
| `POST /api/opc-ingest` devuelve `400 values missing or empty` | `values` debe ser un objeto no vacío |
| Devices no aparecen en TB tras un POST válido | Verificar que el config node `TB Gateway` tenga el token correcto y el broker conecte a `thingsboard:1883` |
| Salida ML silenciada permanentemente | `flow.ML_INFERENCE_URL` no está set. Para setearla en dev (con `NR_ADMIN_ENABLED=true`): `curl -X POST http://localhost:1880/admin/set-ml-url -H "Content-Type: application/json" -d '{"url":"http://<ml-host>:<port>/api/inference"}'` |
| Cambios en `settings.js` no aplican | El archivo se monta como volumen; restart: `docker compose restart nodered_tb` |
