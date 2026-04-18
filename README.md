# TrueData UCAM — Base Module (staging)

Repo de staging de UCAM. Aquí se desarrollan las mejoras al módulo base
(ThingsBoard + Node-RED + deploy pipeline + simulador) antes de portarlas
al monorepo TRUEDATA en gitlab vía Merge Requests.

> **Objetivo actual:** MVP casi-production-ready para la demo INCIBE en
> planta Francisco Aragón (FR_ARAGON). Velocidad > perfección.

## Servicios

| Directorio | Servicio | Puerto |
|---|---|---|
| `truedata-thingsboard/` | ThingsBoard CE 4.1 + Postgres | 9090, 1883, 5432 |
| `truedata-nodered/` | Node-RED 3.1.9 (flow v2) | 1880 |
| `deploy/` | Pipeline Python de provisioning (v1 legacy + v2 WIP) | — |
| `simulator/` | `opc_client_v2.py` — replay del dump OPC-UA de FR_ARAGON contra Node-RED | — |

Servicios comparten la red Docker externa `truedata_iot_network`.

## Arrancar

```sh
docker network create truedata_iot_network    # una sola vez por host
docker compose up -d                           # desde la raíz: TB + Postgres + NR
```

Setup end-to-end (Gateway device, token en NR, profile, validación) en
[docs/SETUP.md](docs/SETUP.md).

## Entrada al código y a los docs

- [CLAUDE.md](CLAUDE.md) — contexto operativo del repo, arquitectura v2,
  trabajo activo, gotchas. Punto de entrada para cualquier sesión de trabajo.
- [docs/architecture/README.md](docs/architecture/README.md) — overview de
  arquitectura + enlaces a los contratos públicos.
- [docs/architecture/ADR-003.md](docs/architecture/ADR-003.md) — decisión
  arquitectónica del pipeline v2.
- [docs/contracts/](docs/contracts/) — **entregable**: contratos públicos al
  resto del consorcio (`opc-ingest`, `ml-inference`, `ml-writeback`,
  `airtrace-writeback`).
- [docs/superpowers/](docs/superpowers/) — specs + plans activos a ejecutar.

## Credenciales dev (rotar en deploy real)

| Servicio | Usuario | Password |
|---|---|---|
| ThingsBoard | `tenant@thingsboard.org` | `tenant` |
| Node-RED | `tenant` | hash en `truedata-nodered/settings.js` |
