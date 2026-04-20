# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo purpose

Este repo (`TrueData-UCAM`) es el **staging del equipo Base** para contribuir al monorepo
`C:\Users\david\TrueData\truedata-gitlab` (módulo `base/`). Aquí se desarrollan e
integran las mejoras del pipeline de ingestión. **Las MRs iniciales de la
contribución ya se entregaron**; a partir de ahora los cambios fluyen
incrementalmente: edición en este repo → copia al clon local del gitlab
→ push al gitlab en la nube cuando estén verdes.

**Objetivo inmediato:** MVP casi-production-ready para la demo regulatoria en planta
Francisco Aragón (FR_ARAGON). Velocidad de implementación > perfección técnica.
Calidad de happy path, no defensiva paranoica.

**Este repo es un puente.** El historial de commits aquí no importa; lo que
importa es lo que termina aterrizando en el monorepo gitlab. No pierdas tiempo
afinando mensajes de commit ni limpieza cosmética.

## Arquitectura (pipeline v2)

El OPC client POSTea bundles HTTP → Node-RED valida, hace LOCF y
despacha en paralelo a ThingsBoard (vía Gateway MQTT API) y al servicio AI
(HTTP fire-and-forget, timeout 5 s).

```
┌──────────────┐  HTTP  ┌──────────────┐  MQTT  ┌──────────────┐
│ OPC Client   │ ─────► │   Node-RED   │ ─────► │ ThingsBoard  │
│              │        │   fn_main    │        │ (source of   │
└──────────────┘        └──────┬───────┘        │  truth)      │
                               │ HTTP (paralelo) └──────────────┘
                               ▼
                        ┌──────────────┐
                        │ AI inference │ ──writeback──► TB
                        └──────────────┘
                                │
                                ▼
                        ┌──────────────┐
                        │  blockchain  │ ──writeback──► TB
                        └──────────────┘
```

**Claves del diseño:** cero cambios en el OPC Client; `sourceTimestamp` del PLC
se preserva end-to-end (client-side ts siempre); fan-out nativo de TB via
Gateway; NR construye snapshot LOCF de cardinalidad fija N antes de llamar al
servicio AI (warm-up gate evita emisiones pre-bootstrap). Detalle en
[docs/architecture/ADR-003.md](docs/architecture/ADR-003.md).

## Layout del repo

```
truedata-thingsboard/   TB CE 4.1.0 + Postgres (docker compose propio)
truedata-nodered/       Node-RED 3.1.9, flow v2 en data/flows.json
deploy/                 Pipeline Python de provisioning v2
  onboarding/             paquete con la lógica (cli, tb, nodered, secrets, …)
  onboard_client_v2.py    shim de compatibilidad → delega en deploy.onboarding.cli
  clients/FR_ARAGON.yaml  manifest del único cliente activo
  secrets/FR_ARAGON/*.env [gitignored, runtime] tokens + flows_cred.json cifrado
  README.md               bring-up + testing instructions
simulator/
  opc_client_v2.py        replay del dump OPC-UA de FR_ARAGON contra NR
src/FR_ARAGON/          Dump real del OPC client (SQL + derived CSV)
docs/architecture/      ADR-003 (decisión v2)
docs/contracts/         ENTREGABLE — contratos públicos al resto del consorcio
docs/testing/           pre-production.md — plan de tests manuales (simulador, regímenes, F1)
docker-compose.yml      Compose raíz — `include:` los dos sub-composes
```

## Pipeline v2 (único activo)

**Cliente único:** FR_ARAGON (planta Francisco Aragón, target de la demo regulatoria).

| Aspecto | v2 (actual) |
|---|---|
| Entrada | `simulator/opc_client_v2.py` — replay del dump OPC-UA contra `POST /api/opc-ingest` de NR |
| Provisioning | `python3 -m deploy.onboarding --manifest deploy/clients/FR_ARAGON.yaml` (idempotente) |
| Transporte a TB | NR pre-TB, Gateway MQTT API con un único token (device `OPC-Gateway`) |
| AI | NR construye snapshot LOCF (cardinalidad fija N=27) y postea a `/api/inference` en paralelo con la persistencia TB |
| Estado | Pipeline v2 GREEN extremo a extremo; bring-up automatizado sin UI clicks (ver `truedata-nodered/README.md`). |

## Estado

Pipeline v2 GREEN extremo a extremo: `deploy/onboarding/` idempotente,
`fn_main` con validación defensiva + LOCF + warmup gate, suite pytest de
integración (26/26) verde. El pipeline v1 se eliminó del repo el 2026-04-18
tras confirmar que su copia canónica vive en el monorepo gitlab.

### Porting al monorepo gitlab (incremental)

Las MRs iniciales de estructura (infra + deploy + simulator) ya aterrizaron
en `truedata-gitlab/base/`. Para cambios posteriores: editar aquí, replicar
el fichero equivalente en el clon local del gitlab, verificar que sigue
compilando/arrancando en el compose monolítico, y hacer push a la nube
cuando esté verde. Sin plan formal — cambio a cambio.

## Contratos (entregable al consorcio)

Los ficheros en `docs/contracts/` son la **interfaz pública** del módulo
base. Se actualizan **al final** (después de que el código v2 esté verde),
no al principio. No regeneres estos docs por defecto.

- [`opc-ingest.md`](docs/contracts/opc-ingest.md) — servicio OPC → NR
- [`ai-service.md`](docs/contracts/ai-service.md) — NR → servicio AI → TB (inferencia + writeback)
- [`blockchain-writeback.md`](docs/contracts/blockchain-writeback.md) — blockchain → TB

## Comandos útiles

### Bring-up del stack

```bash
# Primera vez (fresh clone): un único comando orquesta todo —
# auto-arranca TB+Postgres, crea profiles/devices, escribe secrets,
# auto-arranca NR y valida E2E. Ver docs/SETUP.md para el detalle.
cp .env.example .env          # solo la primera vez
python3 -m deploy.onboarding --manifest deploy/clients/FR_ARAGON.yaml

# Restart cuando los secrets ya existen (p.ej. después de `docker compose down`)
docker compose up -d

# Estado de los servicios (TB tarda 3-5 min la primera migración Postgres)
docker compose ps
```

### Smoke test del endpoint de ingesta

```bash
curl -s -X POST http://localhost:1880/api/opc-ingest \
  -H "Content-Type: application/json" \
  -d "{\"ts\": $(date +%s%3N), \"values\": {\"HEALTHCHECK\": 1}}"
# Esperado: {"status":"ok","tags":1,"inference":"warmup(...)"}
```

### Inyección contra NR con el dump real FR_ARAGON

```bash
python3 simulator/opc_client_v2.py \
  --sql src/FR_ARAGON/Francisco_16_01_2026.sql \
  --url http://localhost:1880/api/opc-ingest \
  --limit 10 --rate burst
```

### Runtime config NR (`runtime_config.json`)

```bash
# Ver config activa
cat truedata-nodered/data/runtime_config.json | jq

# Set URL AI (salida 2 silenciada si se elimina la clave)
python3 - <<'PY'
import json
from pathlib import Path

p = Path("truedata-nodered/data/runtime_config.json")
cfg = json.loads(p.read_text()) if p.exists() else {}
cfg["ai_inference_url"] = "http://ai-advanced:5000/api/inference"
p.write_text(json.dumps(cfg, separators=(",", ":")) + "\n")
print("updated", p)
PY
```

El flow recarga el fichero en la siguiente ingesta sin exponer endpoints admin.

### Login TB y JWT (para scripts y debugging)

```bash
JWT=$(curl -s -X POST http://localhost:9090/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"tenant@thingsboard.org","password":"tenant"}' \
    | jq -r .token)
curl -s -H "X-Authorization: Bearer $JWT" \
    "http://localhost:9090/api/tenant/devices?pageSize=100&page=0" | jq '.data[].name'
```

## Gotchas y convenciones

- **Credenciales por defecto TB:** `tenant@thingsboard.org` / `tenant` (dev).
  Todas las credenciales del repo son de dev — rotarlas en el primer arranque
  del deploy real es responsabilidad del operador.
- **`truedata-nodered/data/flows_cred.json`** está gitignored: lo genera
  el CLI de onboarding automáticamente (AES-256-CTR, con el literal
  `${TB_GATEWAY_TOKEN}` que NR resuelve en runtime). No hace falta tocar
  la UI de NR. Si se borra, re-ejecutar `python3 -m deploy.onboarding` lo regenera.
- **`deploy/secrets/<CLIENT>/*.env`** está gitignored: los tokens per-service
  los genera el CLI de onboarding en runtime (umask por defecto del proceso).
- **`src/FR_ARAGON/*.sql`** es el dump Postgres real del OPC client (vendor
  externo) — fuente empírica de toda la caracterización del pipeline (patrón
  bimodal OPC-UA, cadencia real). No está committeado si supera tamaño.
- **TB Gateway MQTT API** auto-provisiona devices al recibir `v1/gateway/connect`
  con el campo `type` apuntando a un device profile existente. NR hace este
  connect perezosamente (solo la primera vez que ve un tag) cacheando en
  `flow.connectedDevices` (memoria, se vacía al restart de NR).
- **Apuntar `TB_URL` / `NR_URL` a entornos distintos:** todos los scripts de
  `deploy/` y `simulator/` aceptan estas env vars. Default `localhost:9090` /
  `localhost:1880`.
- **Python deps** unificados en `requirements.txt` (raíz):
  `pip install -r requirements.txt` cubre `deploy/`, `simulator/` y los tests
  de integración.

## Docs que merece la pena leer antes de trabajar

1. `docs/architecture/ADR-003.md` — decisión arquitectónica v2 (context + rationale).
2. `docs/contracts/opc-ingest.md`, `ai-service.md`, `blockchain-writeback.md`,
   `secrets-delivery.md` — contratos públicos al resto del consorcio.
3. `docs/SETUP.md` — bring-up desde cero la primera vez.
4. `docs/OPERATIONS.md` — runbook recurrente (rotación, backup, troubleshooting, health).
5. `tests/integration/test_bringup_v2.py` — invariantes accionables post-bring-up.

## Herramientas de la sesión

- **RTK** está instalado globalmente: prefijar commandos con `rtk` da 60-90%
  ahorro de tokens en `git`/`gh`/etc (ver `~/.claude/RTK.md`).
