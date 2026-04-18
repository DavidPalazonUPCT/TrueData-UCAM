# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo purpose

Este repo (`TrueData-UCAM`) es el **staging de UCAM** para contribuir al monorepo
`C:\Users\david\TrueData\truedata-gitlab` (módulo `base/`). Aquí se desarrollan e
integran las mejoras del pipeline de ingestión. **Las MRs iniciales de la
contribución ya se entregaron**; a partir de ahora los cambios fluyen
incrementalmente: edición en este repo → copia al clon local del gitlab
→ push al gitlab en la nube cuando estén verdes.

**Objetivo inmediato:** MVP casi-production-ready para demo INCIBE en planta
Francisco Aragón (FR_ARAGON). Velocidad de implementación > perfección técnica.
Calidad de happy path, no defensiva paranoica.

**Este repo es un puente.** El historial de commits aquí no importa; lo que
importa es lo que termina aterrizando en el monorepo gitlab. No pierdas tiempo
afinando mensajes de commit ni limpieza cosmética.

## Arquitectura (pipeline v2)

OPC Client (Neoradix) POSTea bundles HTTP → Node-RED valida, hace LOCF y
despacha en paralelo a ThingsBoard (vía Gateway MQTT API) y al servicio ML
(HTTP fire-and-forget, timeout 5 s).

```
┌──────────────┐  HTTP  ┌──────────────┐  MQTT  ┌──────────────┐
│ OPC Client   │ ─────► │   Node-RED   │ ─────► │ ThingsBoard  │
│ (Neoradix)   │        │   fn_main    │        │ (source of   │
└──────────────┘        └──────┬───────┘        │  truth)      │
                               │ HTTP (paralelo) └──────────────┘
                               ▼
                        ┌──────────────┐
                        │ ML inference │ ──writeback──► TB
                        └──────────────┘
                                │
                                ▼
                        ┌──────────────┐
                        │   airtrace   │ ──writeback──► TB
                        └──────────────┘
```

**Claves del diseño:** cero cambios en el OPC Client; `sourceTimestamp` del PLC
se preserva end-to-end (client-side ts siempre); fan-out nativo de TB via
Gateway; NR construye snapshot LOCF de cardinalidad fija N antes de llamar a
ML (warm-up gate evita emisiones pre-bootstrap). Detalle en
[docs/architecture/ADR-003.md](docs/architecture/ADR-003.md).

## Layout del repo

```
truedata-thingsboard/   TB CE 4.1.0 + Postgres (docker compose propio)
truedata-nodered/       Node-RED 3.1.9, flow v2 en data/flows.json
deploy/                 Pipeline Python de provisioning v2
  onboard_client_v2.py    CLI de provisioning single-tenant (ver plan onboard-v2)
  requirements.txt        deps: requests, pyyaml, cryptography
  clients/FR_ARAGON.yaml  manifest del único cliente activo
  secrets/FR_ARAGON/*.env [gitignored, runtime] tokens + flows_cred.json cifrado
  README.md               bring-up + testing instructions
simulator/
  opc_client_v2.py        replay del dump OPC-UA de FR_ARAGON contra NR
src/FR_ARAGON/          Dump real del OPC Client Neoradix (SQL + derived CSV)
docs/architecture/      ADR-003 (decisión v2); PLAN-001 (execución v2)
docs/contracts/         ENTREGABLE — contratos públicos al resto del consorcio
docs/operations/        Runbooks operacionales
docs/superpowers/       Specs + plans activos (entradas para writing-plans)
docker-compose.yml      Compose raíz — `include:` los dos sub-composes
```

## Pipeline v2 (único activo)

**Cliente único:** FR_ARAGON (planta Francisco Aragón, target de la demo INCIBE).

| Aspecto | v2 (actual) |
|---|---|
| Entrada | `simulator/opc_client_v2.py` — replay del dump OPC-UA contra `POST /api/opc-ingest` de NR |
| Provisioning | `deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml` (idempotente) |
| Transporte a TB | NR pre-TB, Gateway MQTT API con un único token (device `OPC-Gateway`) |
| ML | NR construye snapshot LOCF (cardinalidad fija N=27) y postea a `/api/inference` en paralelo con la persistencia TB |
| Estado | Pipeline v2 GREEN extremo a extremo; bring-up automatizado sin UI clicks (ver `truedata-nodered/README.md`). Código v1 eliminado del repo el 2026-04-18. |

El pipeline v1 (scripts `env_client.py`, numerados, `APIThingsboard.py`, `Plantillas/`) se eliminó del repo tras confirmar que su copia canónica ya vive en el monorepo gitlab (portada en MR-2). Si se necesita revisitar, consultar el clon local del gitlab.

## Estado y trabajo activo

PLAN-001 (`docs/architecture/PLAN-001.md`): migración v1 → v2 en 6 fases.
Fases 0-3 completadas; quedan:

- **Fase 4** — Eliminar ETLflows + profile_buckets + 6 bucket devices + rule
  chains asociadas (limpieza de capa de agregación).
- **Fase 5** — Tests E2E + cleanup de código legacy.

**Los dos planes activos** (superpowers/) son lo tangible a ejecutar para
llegar a la demo:

1. [`plans/2026-04-17-onboard-client-v2-implementation.md`](docs/superpowers/plans/2026-04-17-onboard-client-v2-implementation.md)
   Sustituye el script ad-hoc `/tmp/fase3_exec.py` por un CLI reproducible
   (`deploy/onboard_client_v2.py`) que toma un manifest YAML por cliente,
   idempotentemente asegura profiles + devices en TB, configura NR, corre
   smoke tests y escribe `.env` per-servicio. Spec:
   [`specs/2026-04-17-onboard-client-v2-design.md`](docs/superpowers/specs/2026-04-17-onboard-client-v2-design.md).

2. [`plans/2026-04-17-v2-pipeline-reliability-fixes.md`](docs/superpowers/plans/2026-04-17-v2-pipeline-reliability-fixes.md)
   Corrige BUG-1/2/3 + LIMIT-2/4 en `fn_main` de `flows.json` y añade una
   suite pytest de 22 casos de integración + runbook F1. Spec:
   [`specs/2026-04-17-v2-pipeline-reliability-fixes-design.md`](docs/superpowers/specs/2026-04-17-v2-pipeline-reliability-fixes-design.md).

Orden recomendado: **reliability-fixes → onboard-client-v2**.

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
- [`ml-inference.md`](docs/contracts/ml-inference.md) — NR → servicio ML
- [`ml-writeback.md`](docs/contracts/ml-writeback.md) — ML → TB
- [`airtrace-writeback.md`](docs/contracts/airtrace-writeback.md) — blockchain → TB

## Comandos útiles

### Bring-up del stack (primera vez)

```bash
# Desde la raíz: levanta TB + Postgres + NR. La red truedata_iot_network
# la crea docker compose automáticamente (bridge interna).
export CLIENT=FR_ARAGON
docker compose up -d

# TB tarda 3-5 min en la primera migración Postgres. El healthcheck del
# compose ya refleja el estado; espera a que ps marque `healthy`:
docker compose ps
```

Setup completo (Gateway, token en NR, profile) en [docs/SETUP.md](docs/SETUP.md).

### Smoke test del endpoint de ingesta

```bash
curl -s -X POST http://localhost:1880/api/opc-ingest \
  -H "Content-Type: application/json" \
  -d "{\"ts\": $(date +%s%3N), \"values\": {\"HEALTHCHECK\": 1}}"
# Esperado: {"status":"ok","tags":1}
```

### Inyección contra NR con el dump real FR_ARAGON

```bash
python3 simulator/opc_client_v2.py \
  --sql src/FR_ARAGON/Francisco_16_01_2026.sql \
  --url http://localhost:1880/api/opc-ingest \
  --limit 10 --rate burst
```

### Admin endpoints NR (solo con `NR_ADMIN_ENABLED=true`)

```bash
# Ver/set tags esperados del snapshot LOCF
curl -s http://localhost:1880/admin/get-expected-tags
curl -s -X POST http://localhost:1880/admin/set-expected-tags \
  -H "Content-Type: application/json" -d '{"tags":["TAG1","TAG2",...]}'

# Ver/set URL ML (salida 2 silenciada si unset)
curl -s http://localhost:1880/admin/get-ml-url
curl -s -X POST http://localhost:1880/admin/set-ml-url \
  -H "Content-Type: application/json" -d '{"url":"http://ml:5000/api/inference"}'
curl -s -X POST http://localhost:1880/admin/clear-ml-url
```

En producción, `NR_ADMIN_ENABLED` **no debe setearse**. Los `/admin/*`
responden `404` byte-identical a un path inexistente.

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
- **`truedata-nodered/data/flows_cred.json`** está gitignored: cifrado con el
  `credentialSecret` de la instancia, no es portable entre hosts. Tras levantar
  NR hay que setear el token del Gateway a mano en la UI (ver
  `truedata-nodered/README.md`).
- **`deploy/secrets/<CLIENT>/*.env`** está gitignored: los tokens per-service
  los genera `onboard_client_v2.py` en runtime y los escribe con mode 0600.
- **`src/FR_ARAGON/*.sql`** es el dump Postgres real del OPC Client de
  Neoradix — fuente empírica de toda la caracterización del pipeline (patrón
  bimodal OPC-UA, cadencia real). No está committeado si supera tamaño.
- **TB Gateway MQTT API** auto-provisiona devices al recibir `v1/gateway/connect`
  con el campo `type` apuntando a un device profile existente. NR hace este
  connect perezosamente (solo la primera vez que ve un tag) cacheando en
  `flow.connectedDevices` (memoria, se vacía al restart de NR).
- **Apuntar `TB_URL` / `NR_URL` a entornos distintos:** todos los scripts de
  `deploy/` y `simulator/` aceptan estas env vars. Default `localhost:9090` /
  `localhost:1880`.
- **Python deps** en cada subdir que lo necesite:
  `pip install -r deploy/requirements.txt` (pendiente de crear, ver plan
  onboard-v2 Task 1).

## Docs que merece la pena leer antes de trabajar

1. `docs/architecture/ADR-003.md` — la decisión arquitectónica v2 (context + rationale).
2. `docs/contracts/opc-ingest.md` y `ml-inference.md` — qué espera/produce NR.
3. `docs/superpowers/specs/*` — qué estamos construyendo ahora.
4. `docs/superpowers/plans/*` — cómo lo vamos a construir, paso a paso.
5. `docs/SETUP.md` — cómo dejar el stack operativo desde cero.

## Herramientas de la sesión

- **Skills activos relevantes:** `truedata-gitlab-contribution` (guía la
  contribución al monorepo), `superpowers:subagent-driven-development`
  (para ejecutar planes con checkpoints), `superpowers:systematic-debugging`.
- **TaskCreate** para trackear ejecución de los planes (cada checkbox ~= task).
- **RTK** está instalado globalmente: prefijar commandos con `rtk` da 60-90%
  ahorro de tokens en `git`/`gh`/etc (ver `~/.claude/RTK.md`).
