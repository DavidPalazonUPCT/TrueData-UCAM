# deploy/

Provisioning pipeline v2 de TRUEDATA. Single-tenant, idempotente,
bring-up sin UI clicks.

- `onboarding/` — paquete Python modular (ver §Estructura del paquete).
  Invocación canónica: `python3 -m deploy.onboarding --manifest <path>`.
- `onboard_client_v2.py` — shim de compatibilidad hacia atrás; delega en
  `deploy.onboarding.cli:main`. Mantiene funcional el comando
  `python3 deploy/onboard_client_v2.py ...` del plan original.
- `clients/<CLIENT>.yaml` — manifests de cliente (uno por planta).
- `secrets/<CLIENT>/*.env` — tokens generados en runtime (gitignored).
  Tres ficheros por cliente: `ai-inference.env`, `blockchain-anchor.env`,
  `nodered-gateway.env`. Los dos primeros los consume el servicio externo
  correspondiente vía Docker `env_file:`. El tercero lo consume
  `truedata-nodered/docker-compose.yml` (inyecta `TB_GATEWAY_TOKEN` como env
  del container NR; NR substituye `${TB_GATEWAY_TOKEN}` en
  `broker_tb.credentials.user` en runtime).
- El script también regenera `truedata-nodered/data/flows_cred.json` con el
  literal `${TB_GATEWAY_TOKEN}` cifrado (AES-256-CTR, `credentialSecret` de
  `settings.js`). Cada ejecución produce un fichero diferente (IV random) pero
  semánticamente equivalente.

### Protección de `deploy/secrets/` (responsabilidad del operador)

El script escribe los ficheros con el **umask por defecto del proceso**
(típicamente produce `rw-r--r--` en Linux, `rwxrwxrwx` en WSL2/NTFS). La
escritura es atómica (tmp + rename) pero **no se fuerza ningún file-mode
POSIX-específico**, para que el código funcione idéntico en todos los OS
(Linux, macOS, Windows, WSL2/NTFS, contenedores, etc.).

La protección real es responsabilidad del operador del host. Opciones
recomendadas (cualquiera basta en un PC embebido single-tenant):

```bash
# Linux/macOS: endurecer el directorio una vez
chmod 700 deploy/secrets
# o en WSL2 sobre NTFS:
# — mover deploy/secrets a un filesystem ext4 (p.ej. /var/lib/truedata/secrets)
# — o aceptar que las perms no se enforcen (MVP: dev machine, no hay secretos reales)
```

El target de la demo regulatoria es un PC embebido Linux donde `chmod 700`
funciona. El dev machine WSL2 no necesita protección equivalente (no hay
secretos de producción allí).

## Estructura del paquete `deploy/onboarding/`

```
deploy/onboarding/
├── __init__.py           # re-exports main(), EXIT_OK
├── __main__.py           # `python3 -m deploy.onboarding` entrypoint
├── cli.py                # parse_args, read_env, main() — orquestador Phases 1-7b
├── manifest.py           # load_manifest + validación del YAML
├── tb.py                 # REST client TB: login, profiles, devices, rotación
├── nodered.py            # runtime_config.json + flows_cred.json (AES-256-CTR)
├── secrets.py            # write_atomic + .env rendering + write_secrets
├── smoke.py              # Phase 6 — smoke tests de AI/blockchain writeback
└── docker_helpers.py     # auto-start de TB + NR via docker compose
```

Una responsabilidad por módulo, sin ciclos de dependencia (todo apunta hacia
`tb.py` y `secrets.py`). El shim `onboard_client_v2.py` preserva
compatibilidad con invocaciones del plan original.

## Bring-up desde máquina limpia (un solo comando)

```bash
# Con .env cargado (CLIENT=FR_ARAGON, TB_ADMIN_PASSWORD=tenant):
python3 -m deploy.onboarding --manifest deploy/clients/FR_ARAGON.yaml
# O (equivalente, vía shim):
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml
```

El CLI orquesta todo:

1. Auto-arranca TB + Postgres via `docker compose up -d thingsboard`
   si no responden (espera hasta ~180 s).
2. Crea/asegura profiles + devices en TB.
3. Escribe los 3 `.env` + `flows_cred.json`.
4. Auto-arranca NR via `docker compose up -d nodered_tb` si no
   responde (espera ~60 s).
5. Configura NR (expected-tags, AI URL) + smoke tests.
6. exit 0 con `onboarding complete`.

Cero pasos manuales en la NR UI, cero `docker compose` a mano. Flags
útiles: `--force` (rota tokens), `--no-autostart` (falla fast si TB/NR
no están up — útil en CI donde el compose ya corre aparte).

## onboard_client_v2.py — Testing Instructions

Pipeline v2 de onboarding para clientes.

### 1. Prerequisites

- TB running: `curl -sf http://localhost:9090/login >/dev/null && echo OK`
- NR running with v2 flow: `curl -sfI http://localhost:1880/ >/dev/null && echo OK`
- Python deps: `pip install -r requirements.txt` (en la raíz del repo)
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
# Expected: 3 files (ai-inference.env, blockchain-anchor.env, nodered-gateway.env).
# File-mode varía por OS/umask — ver nota "Protección de deploy/secrets/" arriba.
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
# Expected: contains Gateway, sensor_planta, inference_input, inference_results, blockchain_anchor (5 profiles)
```

### 6. Verify NR runtime config

```bash
cat truedata-nodered/data/runtime_config.json | python3 -m json.tool
# Expected: expected_tags matches manifest (27 for FR_ARAGON)
#           ai_inference_url matches manifest.ai_inference.url
```

### 7. Force rotation

```bash
OLD=$(grep TB_DEVICE_TOKEN deploy/secrets/FR_ARAGON/ai-inference.env | cut -d= -f2)
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml --force
NEW=$(grep TB_DEVICE_TOKEN deploy/secrets/FR_ARAGON/ai-inference.env | cut -d= -f2)
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
ai-advanced:
  env_file: ./deploy/secrets/FR_ARAGON/ai-inference.env
blockchain:
  env_file: ./deploy/secrets/FR_ARAGON/blockchain-anchor.env
```

Docker inyecta `TB_HOST`, `TB_DEVICE_TOKEN`, etc. como env vars del contenedor. El código del servicio compone `${TB_HOST}/api/v1/${TB_DEVICE_TOKEN}/telemetry`.
