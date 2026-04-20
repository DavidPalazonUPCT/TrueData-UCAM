# deploy/

Provisioning pipeline v2 de TRUEDATA. Single-tenant, idempotente,
bring-up sin UI clicks.

> **Bring-up, healthcheck, rotación, backup/restore** — ver el runbook
> operacional en [`docs/OPERATIONS.md`](../docs/OPERATIONS.md). Este doc
> cubre estructura del paquete + testing del CLI aisladamente.

- `onboarding/` — paquete Python modular con la lógica completa (ver §Estructura del paquete).
  Invocación: `python3 -m deploy.onboarding --manifest <path>`.
- `onboard_client_v2.py` — shim fino (≈15 líneas) que delega en
  `deploy.onboarding.cli:main`. Existe solo para que la ruta
  `python3 deploy/onboard_client_v2.py ...` siga funcionando; toda la
  lógica vive en `onboarding/`.
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
`tb.py` y `secrets.py`).

## Bring-up desde máquina limpia (un solo comando)

```bash
# Con .env cargado (CLIENT=FR_ARAGON, TB_ADMIN_PASSWORD=tenant):
python3 -m deploy.onboarding --manifest deploy/clients/FR_ARAGON.yaml
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

Cero pasos manuales en la NR UI, cero `docker compose` a mano.

### Flags útiles

| Flag | Uso |
|---|---|
| `--dry-run` | Valida manifest + pings, no aplica cambios (ningún fichero escrito) |
| `--force` | Rota tokens TB atómicamente y reescribe los `.env` |
| `--no-autostart` | Falla fast si TB/NR no están up (útil en CI) |

### Verificación post-onboarding

Las invariantes que debe dejar el CLI en TB están automatizadas en
[`tests/integration/test_bringup_v2.py`](../tests/integration/test_bringup_v2.py):

```bash
pytest tests/integration/test_bringup_v2.py -v
# 4 tests: profiles creados, Gateway flag, writeback devices bound a profile correcto
```

### Exit codes

| Code | Significado |
|---|---|
| `0` | OK |
| `1` | Error inesperado (bug) |
| `2` | Input inválido (manifest o env var) |
| `3` | Sistema externo falló (TB/NR) |
| `4` | Smoke test falló |

### Consumo del `.env` por servicios downstream

Contrato formal: [`docs/contracts/secrets-delivery.md`](../docs/contracts/secrets-delivery.md).
Ejemplo multi-servicio: [`docker-compose.example.yml`](../docker-compose.example.yml)
(4-service topology: TB + NR + ai-advanced + blockchain).

Resumen: cada servicio externo carga su `.env` vía `env_file:` en Docker
compose; Docker inyecta `CLIENT`, `TB_HOST`, `TB_DEVICE_NAME`,
`TB_DEVICE_TOKEN` como env vars del contenedor; el código del servicio
compone `${TB_HOST}/api/v1/${TB_DEVICE_TOKEN}/telemetry`. El fichero
`nodered-gateway.env` es **interno de `base/`** — los servicios
externos no deben consumirlo.
