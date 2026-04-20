# ThingsBoard — pipeline v2

ThingsBoard es la fuente de verdad del pipeline v2: recibe telemetría
per-device desde Node-RED vía Gateway MQTT API, persiste timeseries, y
expone los datos a consumidores downstream (dashboards, blockchain,
servicios de inferencia).

- **Imagen:** `thingsboard/tb-postgres:4.1.0`
- **DB:** `postgres:13` (sidecar)
- **Contratos:** [`opc-ingest.md`](../docs/contracts/opc-ingest.md) ·
  [`ai-service.md`](../docs/contracts/ai-service.md) ·
  [`blockchain-writeback.md`](../docs/contracts/blockchain-writeback.md)
- **Setup**: [`docs/SETUP.md`](../docs/SETUP.md)
- **Operaciones** (bring-up, health, rotación, backup, troubleshooting):
  [`docs/OPERATIONS.md`](../docs/OPERATIONS.md)
- **Fuente de verdad de profiles:** `REQUIRED_PROFILES` en
  [`deploy/onboarding/tb.py`](../deploy/onboarding/tb.py)

---

## Puertos

| Puerto | Protocolo | Uso |
|---|---|---|
| 9090 | HTTP | UI web + REST API |
| 1883 | MQTT | Transporte MQTT (incluye Gateway MQTT API) |
| 7070 | gRPC | Transporte Edge/gRPC |
| 5683–5688 | CoAP/UDP | Transporte CoAP |
| 5432 | TCP | PostgreSQL (sidecar `db`) |

---

## Device profiles

El pipeline v2 necesita 5 device profiles en TB. Todos los crea
`python3 -m deploy.onboarding` al primer run (fuente de verdad:
`REQUIRED_PROFILES` en [`deploy/onboarding/tb.py`](../deploy/onboarding/tb.py)).

| Profile | Asignado a | Quién usa el device |
|---|---|---|
| `Gateway` | `OPC-Gateway` device (infra, single-tenant) | NR publica MQTT via este token |
| `sensor_planta` | Devices auto-provisionados per-tag (POT_CCM, TURB1, …) | Node-RED (connect + telemetry) |
| `inference_input` | `inference-input` device (1 por cliente, auto-creado por NR) | Snapshot LOCF que se envía a AI — audit trail |
| `inference_results` | `ai-inference-<cliente>` (1 por cliente) | Servicio AI — writeback de scores |
| `blockchain_anchor` | `blockchain-anchor-<cliente>` (1 por cliente) | Servicio blockchain — writeback de evidencias |

---

## Credenciales por defecto (dev)

| Rol | Usuario | Password |
|---|---|---|
| System Admin | `sysadmin@thingsboard.org` | `sysadmin` |
| Tenant Admin | `tenant@thingsboard.org` | `tenant` |

| Servicio | Usuario | Password |
|---|---|---|
| PostgreSQL | `thingsboard` | `thingsboard_password` |

Todas estas credenciales deben rotarse en el primer arranque de un
deploy real. Procedimiento en
[`docs/OPERATIONS.md §4.3`](../docs/OPERATIONS.md#43-rotar-la-password-admin-de-tb).

---

## Standalone bring-up (solo para debug aislado)

Para el pipeline completo, usar `python3 -m deploy.onboarding` desde la
raíz del repo — ver [`docs/OPERATIONS.md §2`](../docs/OPERATIONS.md#2-bring-up-canónico).

Este modo solo levanta TB + Postgres, sin NR ni onboarding. Útil para:
inspeccionar profiles existentes, probar upgrade de TB, debug de rule
chains.

```sh
docker compose up -d
```

La red `truedata-net` la crea Compose automáticamente.
