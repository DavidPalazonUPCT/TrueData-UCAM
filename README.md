# TrueData UCAM — Base Module

UCAM's base-module contribution to the TRUEDATA project: ThingsBoard for
device/telemetry management, Node-RED for ETL aggregation, a Python deploy
pipeline for client provisioning, and a sensor simulator for DEMO mode.

This is UCAM's source repo. Production code is contributed to the TRUEDATA
GitLab monorepo via Merge Requests; the contribution roadmap lives at
`docs/superpowers/plans/2026-04-14-truedata-gitlab-base-contribution.md`.

## Service Architecture

Services share an external Docker network `truedata_iot_network`.

| Directory | Services | Port |
|---|---|---|
| `truedata-thingsboard/` | ThingsBoard + PostgreSQL | 9090, 1883, 7070, 5432 |
| `truedata-nodered/`     | Node-RED                 | 1880 |

Detailed module guides:
- [ThingsBoard guide](truedata-thingsboard/README.md)
- [Node-RED guide](truedata-nodered/README.md)

## Documentation

Integration contracts (for external consumers):
- [`POST /api/opc-ingest`](docs/contracts/opc-ingest.md) — cliente OPC
  → Node-RED.
- [`POST /api/inference`](docs/contracts/ml-inference.md) — Node-RED
  → servicio ML.

Per-service documentation lives next to each service:
- [`truedata-thingsboard/`](truedata-thingsboard/README.md) — README
  + complementary docs (e.g. `DEVICE-PROFILE.md`).
- [`truedata-nodered/`](truedata-nodered/README.md) — README +
  complementary docs (e.g. `SETUP.md`).

## Project structure

```
deploy/                  Python deploy pipeline (provision a TB+Node-RED client)
truedata-thingsboard/    ThingsBoard service definition
truedata-nodered/        Node-RED service definition + settings.js
simulator/               simulador_sensores.py — DEMO injector for ThingsBoard
system_sizing/           INCIBE sizing calculator
fetch_tokens_remote.py   Operational tool: regenerate TB device access tokens
DockerfileEnvClient      Container image for `deploy/env_client.py`
INJECTION_SETUP.md       Simulator runbook (remote-TB injection flow)
SIMULATION_GUIDE.md      Simulator usage reference
DEPLOYMENT_GUIDE.md      Step-by-step deployment guide (Spanish)
```

## Setup and Deployment

### Step 0: Create the shared network.

```sh
docker network create --driver=bridge --subnet=172.25.0.0/24 truedata_iot_network
```

### Step 1: Start ThingsBoard (must be first).

```sh
cd truedata-thingsboard
docker compose up -d
```

Wait until `http://localhost:9090` responds (first boot can take 3–5 min
while the DB initializes). If you hit permissions errors in `tb-data/db`:

```sh
sudo chmod -R 777 tb-data
sudo chmod 750 tb-data/db
```

Then restart: `docker compose up -d`.

### Step 2: Start Node-RED.

```sh
cd truedata-nodered
docker compose up -d
```

`settings.js` is mounted automatically via volume. Check `http://localhost:1880`.

### Step 3: Provision a client.

`deploy/Client.json` carries the client name and model. Configure the URLs in
the scripts under `deploy/`, then run the master script:

```sh
python3 deploy/env_client.py
```

It chains the numbered scripts:

| Script | Purpose |
|---|---|
| `1_Configuracion_General.py`                   | General config + base aggregation flows |
| `1.1_Subir_Niveles_Criticidad_Inicial_Bulk.py` | Initial criticality levels (bulk) |
| `2_Crear_Entorno_Cliente_ThingsBoard.py`       | Devices + buckets in TB |
| `2.2_Crear_ETL_NodeRed_Cliente.py`             | Per-client ETL flows in Node-RED |
| `3_Solicitar_Niveles_Criticidad.py`            | Inspect criticality levels (read) |
| `3.1_Modificar_Niveles_Criticidad.py`          | Modify criticality levels |
| `4_Subir_thresholds.py`                        | Upload model thresholds *(see note)* |

> [!NOTE]
> `4_Subir_thresholds.py` reads CSV inputs from a path that previously lived
> under `src/models/` (no longer in this repo, since training/inference is
> out of UCAM's base-module scope). Until the input location is refactored
> to a base-owned path, that step requires the CSVs to be made available
> externally.

### Step 4 (DEMO): Run the simulator.

```sh
python3 simulator/simulador_sensores.py --client ESAMUR
```

See `SIMULATION_GUIDE.md` and `INJECTION_SETUP.md`.

## Scope

This repo holds UCAM's base-module work: TB, Node-RED, deploy pipeline,
simulator, INCIBE sizing calculator. Training/inference (CoGNN/STGNN) was
previously vendored here but is now out of scope; see the
`baseline-pre-contribution` tag for the historical state with ML included.
