# Setup end-to-end — Node-RED + ThingsBoard

Levantar el pipeline v2 desde un repo recién clonado hasta el primer
`POST /api/opc-ingest` validado, con **un único comando** del CLI de
onboarding. El script detecta que TB y/o NR no están arriba y los
lanza automáticamente vía `docker compose up -d`, luego continúa con
profiles, devices, secrets, configuración y smoke tests.

> **Para operaciones recurrentes** (rotación de tokens, backup/restore,
> troubleshooting, healthcheck detallado): ver
> [`docs/OPERATIONS.md`](OPERATIONS.md).

**Pre-requisitos del host:**

- Docker Engine + Docker Compose v2.20+
- Python 3.9+ con `pip install -r requirements.txt`
- `curl`, `jq` (opcional, para verificación manual)

---

## 1. Cargar el `.env` local

```sh
# bash/zsh
cp .env.example .env
set -a && source .env && set +a

# PowerShell
Copy-Item .env.example .env
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
    [Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
  }
}
```

**Pass:** `echo $CLIENT` (bash) o `$env:CLIENT` (PS) imprime
`FR_ARAGON`. Idem `TB_ADMIN_PASSWORD`.

---

## 2. Bring-up completo (un solo comando)

```sh
python3 -m deploy.onboarding --manifest deploy/clients/FR_ARAGON.yaml
```

La lógica vive en el paquete [`deploy/onboarding/`](../deploy/README.md).
El CLI hace todo el trabajo en orden:

1. Valida manifest + lee env vars.
2. **Auto-arranca TB + Postgres** si no responden en `$TB_URL`
   (`docker compose up -d thingsboard`; espera hasta ~180 s el primer
   arranque mientras Postgres migra).
3. Login TB + crea/asegura los 5 device profiles (`Gateway`,
   `sensor_planta`, `inference_input`, `inference_results`,
   `blockchain_anchor`).
4. Crea/asegura los 3 devices (`ai-inference-FR_ARAGON`,
   `blockchain-anchor-FR_ARAGON`, `OPC-Gateway`) y captura sus tokens.
5. Escribe `deploy/secrets/FR_ARAGON/*.env` (3 ficheros) y
   `truedata-nodered/data/flows_cred.json` (cifrado AES-256-CTR con
   `credentialSecret` de `settings.js`).
6. **Auto-arranca NR** si no responde en `$NR_URL`
   (`docker compose up -d nodered_tb`; hasta 60 s).
7. Configura NR (set-expected-tags + set-ai-url o clear).
8. Smoke tests contra TB (POST telemetry + verify persistence en
   `ai-inference-FR_ARAGON` y `blockchain-anchor-FR_ARAGON`).

**Pass:** `exit=0`, stdout termina con `onboarding complete`.

Para rotar tokens en demanda: añadir `--force`.
Para skipping de auto-start (útil en CI): añadir `--no-autostart`.

---

## 3. Validación end-to-end

```sh
TS=$(date +%s%3N)
curl -s -X POST http://localhost:1880/api/opc-ingest \
    -H "Content-Type: application/json" \
    -d "{\"ts\": $TS, \"values\": {\"POT_CCM\": 42.0}}"
# Esperado: {"status":"ok","tags":1,...}
```

Verifica que el device se auto-provisionó con el profile correcto:

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

## 4. (Opcional) Apuntar la salida AI a un servicio real

Por defecto la salida 2 (AI) queda silenciada si
`manifest.ai_inference.url` era `null` al onboardear. Para activarla
en runtime sin re-onboardear, editar `truedata-nodered/data/runtime_config.json`:

```sh
python3 - <<'PY'
import json
from pathlib import Path

p = Path("truedata-nodered/data/runtime_config.json")
cfg = json.loads(p.read_text()) if p.exists() else {}
cfg["ai_inference_url"] = "http://<ai-host>:<port>/api/inference"
p.write_text(json.dumps(cfg, separators=(",", ":")) + "\n")
print("updated", p)
PY
```

El flow recarga este fichero en la siguiente ingesta.

---

## Cleanup completo (volver a cero)

```sh
docker compose down -v
rm -rf deploy/secrets truedata-nodered/data/flows_cred.json
```
