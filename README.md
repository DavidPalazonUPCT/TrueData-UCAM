# TrueData — Base Module (staging)

Repo de staging del equipo Base. Aquí se desarrollan las mejoras al módulo
base (ThingsBoard + Node-RED + deploy pipeline + simulador) antes de
portarlas al monorepo TRUEDATA en gitlab vía Merge Requests.

> **Objetivo actual:** MVP casi-production-ready para la demo regulatoria
> en planta Francisco Aragón (FR_ARAGON). Velocidad > perfección.

## Servicios

| Directorio | Servicio | Puerto |
|---|---|---|
| `truedata-thingsboard/` | ThingsBoard CE 4.1 + Postgres | 9090, 1883, 5432 |
| `truedata-nodered/` | Node-RED 3.1.9 (flow v2) | 1880 |
| `deploy/` | Paquete Python de provisioning v2 (`deploy/onboarding/`, invocable con `python3 -m deploy.onboarding`) | — |
| `simulator/` | `opc_client_v2.py` — replay del dump OPC-UA de FR_ARAGON contra Node-RED | — |

Los servicios comparten la red Docker interna `truedata-net` (la crea
Compose automáticamente al primer `up`).

## Arrancar

```sh
# Primera vez (fresh clone): un único comando levanta todo
cp .env.example .env
python3 -m deploy.onboarding --manifest deploy/clients/FR_ARAGON.yaml

# Restart cuando los secrets ya existen
docker compose up -d
```

Setup end-to-end completo en [docs/SETUP.md](docs/SETUP.md); invariantes
post-onboarding en [`tests/integration/test_bringup_v2.py`](tests/integration/test_bringup_v2.py).

## Entrada al código y a los docs

- [CLAUDE.md](CLAUDE.md) — contexto operativo del repo, arquitectura v2,
  trabajo activo, gotchas. Punto de entrada para cualquier sesión de trabajo.
- [docs/architecture/ADR-003.md](docs/architecture/ADR-003.md) — decisión
  arquitectónica del pipeline v2 (contiene el diagrama canónico).
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — runbook operacional: bring-up,
  healthchecks, rotación de tokens, backup/restore, troubleshooting.
- [docs/contracts/](docs/contracts/) — **entregable**: contratos públicos al
  resto del consorcio (`opc-ingest`, `ai-service`, `blockchain-writeback`,
  `secrets-delivery`).

## Credenciales dev (rotar en deploy real)

| Servicio | Usuario | Password |
|---|---|---|
| ThingsBoard | `tenant@thingsboard.org` | `tenant` |
| Node-RED | `tenant` | hash en `truedata-nodered/settings.js` |
