# Node-RED — pipeline v2

Node-RED es el pre-procesador y router del pipeline v2: recibe el scan
bulk del OPC Client vía HTTP, publica telemetría a ThingsBoard por
Gateway MQTT API, y dispara la inferencia AI en paralelo.

- **Imagen:** `nodered/node-red:3.1.9`
- **Puerto:** `1880` (editor + endpoints HTTP)
- **Contratos:** [`opc-ingest.md`](../docs/contracts/opc-ingest.md) ·
  [`ai-service.md`](../docs/contracts/ai-service.md)
- **Setup**: [`docs/SETUP.md`](../docs/SETUP.md)
- **Operaciones** (bring-up, health, rotación, backup, troubleshooting):
  [`docs/OPERATIONS.md`](../docs/OPERATIONS.md)

---

## Qué expone

| Endpoint | Método | Descripción | Contrato |
|---|---|---|---|
| `/api/opc-ingest` | POST | Ingesta de scan bulk del OPC Client | [opc-ingest.md](../docs/contracts/opc-ingest.md) |
| `/` | GET | Editor Node-RED (UI) | — |

La configuración runtime (tags esperados y URL AI) se carga desde
`data/runtime_config.json` en cada ingest — sin endpoints admin
expuestos. Para modificarla en caliente ver
[`docs/OPERATIONS.md §5`](../docs/OPERATIONS.md#5-cambiar-configuración-runtime-de-nr).

---

## Estructura del flow (`OPC Ingest v2`)

```
[http-in /api/opc-ingest]
         │
         ▼
[function: validate + connects + telemetry + ai + ack]
         │
         ├──► Salida 1 → [mqtt-out → v1/gateway/telemetry (+ connect)]
         │
         ├──► Salida 2 → [http-request → AI inference API]
         │
         └──► Salida 3 → [http-response 200/400]
```

El function node vive embebido en `data/flows.json`. Pasos internos:

1. **Validación:** `ts` debe ser `typeof "number"` finito dentro de
   `[now-30d, now+5min]`; `values` debe ser objeto no vacío. Si no, sale
   por la salida 3 con `400`.
2. **Connect lazy:** para cada tag que NR no ha visto antes en este
   runtime, publica un `v1/gateway/connect` con
   `{device: <tag>, type: <DEVICE_PROFILE>}`. TB auto-crea el device
   con el profile indicado. Cache en `flow.connectedDevices` (memoria;
   se vacía en restart).
3. **Telemetry:** publica `v1/gateway/telemetry` con
   `{<tag>: [{ts, values: {value}}]}` para todos los tags del scan, con
   el mismo `ts` client-side.
4. **AI paralelo:** si `ai_inference_url` está set en
   `runtime_config.json`, postea `{ts, sensors: values}` con timeout 5 s
   (fire-and-forget).
5. **Ack:** responde `{status: "ok", tags: N, inference: "<estado>"}`
   al cliente OPC (`inference`: `"emitted"` | `"warmup(M/N)"` |
   `"disabled"`).

---

## Variables de entorno y de flow

| Fuente | Variable | Default | Descripción |
|---|---|---|---|
| `docker-compose.yml` (env) | `TZ` | `Europe/Madrid` | Zona horaria |
| `docker-compose.yml` (env) | `NR_RUNTIME_CONFIG_PATH` | `/data/runtime_config.json` | Ruta del JSON runtime leído por `fn_main` |
| Runtime JSON | `expected_tags` | `[]` | Tags para warm-up/LOCF del snapshot de inferencia |
| Runtime JSON | `ai_inference_url` | unset | URL del servicio AI. Si unset, salida 2 silenciada |
| Flow context | `DEVICE_PROFILE` | `sensor_planta` | Profile TB con el que NR auto-provisiona devices |
| Flow context | `connectedDevices` | `{}` | Cache en memoria de devices ya conectados (se vacía en restart) |

---

## Credenciales (dev)

| Campo | Valor |
|---|---|
| URL editor | `http://localhost:1880` |
| Usuario | `tenant` |
| Password | hash bcrypt almacenado en `settings.js`. No recuperable desde el hash |
| `credentialSecret` | definido en `settings.js`. No cambiar post-deploy: invalida `flows_cred.json` |

Regenerar password del editor: ver
[`docs/OPERATIONS.md §10`](../docs/OPERATIONS.md#10-regenerar-password-del-editor-nr).
