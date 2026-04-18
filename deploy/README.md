# deploy/

Provisioning scripts for TRUEDATA UCAM.

- `env_client.py` + `1_*.py` / `2_*.py` / `3_*.py` / `4_*.py` — v1 legacy orchestrator (sirve ESAMUR). No tocar.
- `onboard_client_v2.py` — v2 pipeline (FR_ARAGON y nuevos clientes). Ver sección de abajo.
- `clients/<CLIENT>.yaml` — manifests de cliente (v2).
- `secrets/<CLIENT>/*.env` — tokens generados en runtime (gitignored, mode 0600).
  Tres ficheros por cliente: `ml-inference.env`, `airtrace-anchor.env`,
  `nodered-gateway.env`. Los dos primeros los consume el servicio externo
  correspondiente vía Docker `env_file:`. El tercero lo consume
  `truedata-nodered/docker-compose.yml` (inyecta `TB_GATEWAY_TOKEN` como env
  del container NR; NR substituye `${TB_GATEWAY_TOKEN}` en
  `broker_tb.credentials.user` en runtime).
- El script también regenera `truedata-nodered/data/flows_cred.json` con el
  literal `${TB_GATEWAY_TOKEN}` cifrado (AES-256-CTR, `credentialSecret` de
  `settings.js`). Cada ejecución produce un fichero diferente (IV random) pero
  semánticamente equivalente.

## Bring-up desde máquina limpia

```bash
# Una sola vez en el host:
docker network create truedata_iot_network

# Levanta TB+Postgres (no necesita CLIENT):
docker compose up -d thingsboard

# Onboarding del cliente:
export TB_ADMIN_PASSWORD=tenant
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml

# NR: requiere CLIENT (path del env_file). Operador lo exporta o añade al `.env` raíz.
export CLIENT=FR_ARAGON
cd truedata-nodered && docker compose up -d && cd ..
```

Cero pasos manuales en la NR UI.

## onboard_client_v2.py — Testing Instructions

Pipeline v2 de onboarding para clientes. Spec: [`docs/superpowers/specs/2026-04-17-onboard-client-v2-design.md`](../docs/superpowers/specs/2026-04-17-onboard-client-v2-design.md).

### 1. Prerequisites

- TB running: `curl -sf http://localhost:9090/login >/dev/null && echo OK`
- NR running with v2 flow: `curl -sf http://localhost:1880/admin/get-expected-tags && echo OK`
- Python deps: `pip install -r deploy/requirements.txt`
- Admin password exported:
  ```bash
  export TB_ADMIN_PASSWORD=tenant   # default TB CE
  ```

### 2. Dry-run (no side effects)

```bash
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml --dry-run
# Expected: exit 0, stdout shows "[dry-run] would create: ..."
```

Verify no files written:
```bash
ls deploy/secrets/ 2>/dev/null || echo "no secrets dir yet (OK)"
```

### 3. Happy path

```bash
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml
# Expected: exit 0, stdout ends with "onboarding complete"
ls -la deploy/secrets/FR_ARAGON/
# Expected: 2 files mode -rw-------
```

### 4. Idempotency

```bash
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml
# Expected: exit 0, stdout shows [=] on every profile and device (no [✓] created)
```

### 5. Verify TB state

```bash
JWT=$(curl -s -X POST http://localhost:9090/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"tenant@thingsboard.org","password":"'$TB_ADMIN_PASSWORD'"}' | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])")
curl -s "http://localhost:9090/api/deviceProfiles?pageSize=100&page=0" \
    -H "X-Authorization: Bearer $JWT" | python3 -m json.tool | grep '"name"'
# Expected: contains sensor_planta, inference_input, inference_results, blockchain_anchor
```

### 6. Verify NR state

```bash
curl -s http://localhost:1880/admin/get-expected-tags | python3 -m json.tool
# Expected: expectedCount matches manifest (27 for FR_ARAGON)
curl -s http://localhost:1880/admin/get-ml-url
# Expected: matches manifest.ml_inference.url
```

### 7. Force rotation

```bash
OLD=$(grep TB_DEVICE_TOKEN deploy/secrets/FR_ARAGON/ml-inference.env | cut -d= -f2)
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml --force
NEW=$(grep TB_DEVICE_TOKEN deploy/secrets/FR_ARAGON/ml-inference.env | cut -d= -f2)
[ "$OLD" != "$NEW" ] && echo "rotated OK"
# Expected: "rotated OK"

# Verify old invalidated
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  "http://localhost:9090/api/v1/${OLD}/telemetry" \
  -H "Content-Type: application/json" -d '{"ts":0,"values":{}}'
# Expected: 401
```

### Exit codes (spec §6.4)

| Code | Significado |
|---|---|
| `0` | OK |
| `1` | Error inesperado (bug) |
| `2` | Input inválido (manifest o env var) |
| `3` | Sistema externo falló (TB/NR) |
| `4` | Smoke test falló |

### Consumo del `.env` por servicios downstream

Docker compose directiva `env_file:`:
```yaml
ml-classical:
  env_file: ./deploy/secrets/FR_ARAGON/ml-inference.env
blockchain-api:
  env_file: ./deploy/secrets/FR_ARAGON/airtrace-anchor.env
```

Docker inyecta `TB_HOST`, `TB_DEVICE_TOKEN`, etc. como env vars del contenedor. El código del servicio compone `${TB_HOST}/api/v1/${TB_DEVICE_TOKEN}/telemetry`.
