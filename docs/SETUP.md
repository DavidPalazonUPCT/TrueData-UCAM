# Setup end-to-end — Node-RED + ThingsBoard

Checklist para levantar el pipeline v2 desde un repo recién clonado
hasta el primer `POST /api/opc-ingest` validado. El bring-up es
automatizado: no se tocan UIs ni se copian tokens a mano.

**Pre-requisitos del host:**

- Docker Engine + Docker Compose v2.20+
- Python 3.9+ con `pip install -r deploy/requirements.txt`
- `curl`, `jq` (opcional pero recomendado)

---

## 1. Red Docker externa

Una sola vez por host:

```sh
docker network create truedata_iot_network
```

---

## 2. Levantar ThingsBoard + Postgres

```sh
docker compose up -d thingsboard
```

El primer arranque tarda ~90 s mientras la DB ejecuta migraciones.
Node-RED **todavía no** — hay que onboardear primero para que exista
el token del Gateway device que NR consume vía `env_file`.

---

## 3. Esperar a que la API REST de TB responda

```sh
until curl -sf -o /dev/null -X POST http://localhost:9090/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"tenant@thingsboard.org","password":"tenant"}'; do
  sleep 5
done
```

---

## 4. Onboarding del cliente

`onboard_client_v2.py` provisiona idempotentemente en TB los 4 device
profiles (`sensor_planta`, `inference_input`, `inference_results`,
`blockchain_anchor`), el device tipo Gateway (`OPC-Gateway`), y los 2
devices de writeback (`ml-inference-<CLIENT>`,
`airtrace-anchor-<CLIENT>`). Escribe los tokens a
`deploy/secrets/<CLIENT>/*.env` (mode 0600) y regenera
`truedata-nodered/data/flows_cred.json` con el literal
`${TB_GATEWAY_TOKEN}` cifrado (AES-256-CTR, `credentialSecret` de
`settings.js`).

```sh
export TB_ADMIN_PASSWORD=tenant   # default TB CE en dev
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml
```

Esperado: exit 0, stdout termina con `onboarding complete`. Verifica
los artefactos:

```sh
ls -la deploy/secrets/FR_ARAGON/
# 3 ficheros mode -rw------- (ml-inference.env, airtrace-anchor.env,
# nodered-gateway.env)
```

Para rotar tokens en demanda: añadir `--force`.

---

## 5. Levantar Node-RED

NR consume `deploy/secrets/${CLIENT}/nodered-gateway.env` vía
`env_file:` del compose. `${CLIENT}` tiene que estar seteado en el
entorno del operador (o en un `.env` en la raíz del repo):

```sh
export CLIENT=FR_ARAGON
cd truedata-nodered && docker compose up -d && cd ..
```

NR arranca con el token del Gateway ya inyectado como env var y el
flow cargado desde `data/flows.json`. Cero clicks en la UI.

---

## 6. Validación end-to-end

```sh
curl -s -X POST http://localhost:1880/api/opc-ingest \
    -H "Content-Type: application/json" \
    -d "{\"ts\": $(date +%s%3N), \"values\": {\"POT_CCM\": 42.0}}"
# Esperado: {"status":"ok","tags":1}
```

Verifica que el device `POT_CCM` aparece en TB con el profile
correcto:

```sh
JWT=$(curl -s -X POST http://localhost:9090/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"tenant@thingsboard.org","password":"tenant"}' \
    | jq -r .token)
curl -s "http://localhost:9090/api/tenant/devices?deviceName=POT_CCM" \
    -H "X-Authorization: Bearer $JWT" | jq '{name, type}'
# Esperado: {"name": "POT_CCM", "type": "sensor_planta"}
```

---

## 7. (Opcional) Apuntar la salida ML a un servicio real

Por defecto la salida 2 (ML) queda silenciada si
`manifest.ml_inference.url` era `null` al onboardear. Para activarla
en runtime sin re-onboardear (requiere `NR_ADMIN_ENABLED=true`, ya
seteado en `truedata-nodered/docker-compose.yml` para entornos dev):

```sh
curl -s -X POST http://localhost:1880/admin/set-ml-url \
    -H "Content-Type: application/json" \
    -d '{"url":"http://<ml-host>:<port>/api/inference"}'
```

En producción `NR_ADMIN_ENABLED` no debe setearse — los `/admin/*`
responden `404` byte-identical a un path inexistente.
