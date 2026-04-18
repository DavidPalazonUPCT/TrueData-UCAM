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

### Configuración del broker MQTT (automatizada)

El flow contiene un config node `TB Gateway` que conecta a
`thingsboard:1883` con el access token del device `OPC-Gateway`.
**Todo el flow es reproducible desde cero** — no hay pasos manuales en la UI:

1. `deploy/onboard_client_v2.py` crea (idempotente) el device `OPC-Gateway` en TB.
2. El mismo script escribe `deploy/secrets/<CLIENT>/nodered-gateway.env` con
   `TB_GATEWAY_TOKEN=<token>` y regenera
   `truedata-nodered/data/flows_cred.json` (cifrado AES-256-CTR con
   `credentialSecret=airtrace` de `settings.js`) con el literal
   `${TB_GATEWAY_TOKEN}` en `broker_tb.credentials.user`. Los ficheros se
   escriben con el umask por defecto del proceso; la protección al nivel
   del filesystem es responsabilidad del operador (ver nota en
   [`deploy/README.md`](../deploy/README.md)).
3. `docker-compose.yml` inyecta el token via `env_file` (path parametrizado
   por `${CLIENT}`). NR substituye `${TB_GATEWAY_TOKEN}` en runtime al
   cargar el flow → MQTT auth contra TB.

Bring-up completo desde una máquina limpia:

```sh
docker network create truedata_iot_network
docker compose up -d thingsboard        # desde raíz, arranca TB+Postgres
export TB_ADMIN_PASSWORD=tenant
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml
export CLIENT=FR_ARAGON                  # o añadir al .env raíz
cd truedata-nodered && docker compose up -d
```

Para rotar el token: `--force` en el onboarding (regenera cred file + env file).

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
| Password | hash bcrypt almacenado en `settings.js`. No recuperable desde el hash. Si se pierde: regenerar y reescribir (ver abajo) |
| `credentialSecret` | definido en `settings.js`. No cambiar post-deploy: invalida los credentials cifrados de `flows_cred.json` |

### Regenerar la password del editor NR

```sh
node -e "console.log(require('bcryptjs').hashSync('tu_password', 8))"
# pegar el hash en settings.js → adminAuth.users[0].password
docker compose restart nodered_tb
```

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

## Logs

```sh
# Logs en vivo de NR
docker compose logs -f nodered_tb

# Último arranque (útil para ver errores de MQTT auth)
docker compose logs --tail=200 nodered_tb | grep -iE 'mqtt|auth|error'
```

## Troubleshooting

| Problema | Causa probable / mitigación |
|---|---|
| `POST /api/opc-ingest` devuelve `400 body not valid JSON object` | Body ausente o no parseable como JSON. Verificar `Content-Type: application/json` y que el body no esté vacío |
| `POST /api/opc-ingest` devuelve `400 ts missing or not finite number` | `ts` debe ser Unix ms (`number`, finito). Ver [contracts/opc-ingest.md](../docs/contracts/opc-ingest.md) |
| `POST /api/opc-ingest` devuelve `400 ts outside acceptable window` | `ts` fuera de `[now-30d, now+5min]`. Típico al replayear dumps antiguos: usar `simulator/opc_client_v2.py --shift-to-now` |
| `POST /api/opc-ingest` devuelve `400 values must be non-empty object` | `values` debe ser un objeto JSON no vacío (no array, no null) |
| Devices no aparecen en TB tras un POST válido | Verificar que `TB_GATEWAY_TOKEN` esté inyectado (`docker exec truedata-nodered-nodered_tb-1 printenv TB_GATEWAY_TOKEN`) y que el broker conecte a `thingsboard:1883` (logs de NR) |
| `flows_cred.json` corrupto o desaparecido | Re-ejecutar `python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml` — lo regenera idempotentemente |
| Salida ML silenciada permanentemente | `flow.ML_INFERENCE_URL` no está set. Para setearla en dev (con `NR_ADMIN_ENABLED=true`): `curl -X POST http://localhost:1880/admin/set-ml-url -H "Content-Type: application/json" -d '{"url":"http://<ml-host>:<port>/api/inference"}'` |
| Cambios en `settings.js` no aplican | El archivo se monta como volumen; restart: `docker compose restart nodered_tb` |
