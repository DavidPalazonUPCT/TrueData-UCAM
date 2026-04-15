# File Mapping: UCAM Source → GitLab Destination

Quick-reference lookup for which source files go where during porting.

## MR-1: Infrastructure

| Source (TrueData-UCAM/) | Destination (truedata-gitlab/) | Action |
|---|---|---|
| `truedata-thingsboard/docker-compose.yml` | `base/docker-compose.override.yml` | Merge (extract TB service config) |
| `truedata-thingsboard/` config mounts | `base/thingsboard/config/` | Copy if present |
| `truedata-nodered/settings.js` | `base/node-red/settings.js` | Port + sanitize |
| `truedata-nodered/docker-compose.yml` | `base/docker-compose.override.yml` | Merge (extract NR service config) |
| — | `base/thingsboard/Dockerfile` | Create new |
| — | `base/thingsboard/README.md` | Create new |
| — | `base/node-red/Dockerfile` | Create new |
| — | `base/node-red/flows/.gitkeep` | Create new |
| — | `base/node-red/README.md` | Create new |
| — | `base/docker-compose.override.yml` | Create new |
| — | `base/README.md` | Rewrite existing scaffold |
| — | `.env.example` | Append base vars |

## MR-2: Deploy Pipeline

| Source (TrueData-UCAM/) | Destination (truedata-gitlab/) | Action |
|---|---|---|
| `deploy/APIThingsboard.py` | `base/deploy/APIThingsboard.py` | Port + sanitize |
| `deploy/env_client.py` | `base/deploy/env_client.py` | Port + sanitize |
| `deploy/1_Configuracion_General.py` | `base/deploy/1_Configuracion_General.py` | Port + sanitize |
| `deploy/1.1_Subir_Niveles_Criticidad_Inicial_Bulk.py` | `base/deploy/1.1_Subir_Niveles_Criticidad_Inicial_Bulk.py` | Port + sanitize |
| `deploy/2_Crear_Entorno_Cliente_ThingsBoard.py` | `base/deploy/2_Crear_Entorno_Cliente_ThingsBoard.py` | Port + sanitize |
| `deploy/2.2_Crear_ETL_NodeRed_Cliente.py` | `base/deploy/2.2_Crear_ETL_NodeRed_Cliente.py` | Port + sanitize |
| `deploy/3_Solicitar_Niveles_Criticidad.py` | `base/deploy/3_Solicitar_Niveles_Criticidad.py` | Port + sanitize |
| `deploy/3.1_Modificar_Niveles_Criticidad.py` | `base/deploy/3.1_Modificar_Niveles_Criticidad.py` | Port + sanitize |
| `deploy/4_Subir_thresholds.py` | `base/deploy/4_Subir_thresholds.py` | Port + sanitize |
| `deploy/Plantillas/` | `base/deploy/Plantillas/` | Copy tree + check for tokens |
| `deploy/Client.json` (genericized) | `base/deploy/TEMPLATE/Client.json` | Create new (generic) |
| — | `base/deploy/TEMPLATE/DeviceImport.csv.example` | Create new |
| — | `base/deploy/TEMPLATE/Niveles_de_Criticidad.csv.example` | Create new |
| — | `base/deploy/TEMPLATE/README.md` | Create new |
| — | `base/deploy/requirements.txt` | Create new |
| — | `base/deploy/README.md` | Create new |
| — | `.gitignore` | Append client data patterns |

## MR-3: Simulator + OPC Contract

| Source (TrueData-UCAM/) | Destination (truedata-gitlab/) | Action |
|---|---|---|
| `src/dataloader/simulador_sensores.py` | `shared/simulator/src/simulador_sensores.py` | Port + sanitize |
| — | `shared/simulator/Dockerfile` | Create new |
| — | `shared/simulator/requirements.txt` | Create new |
| — | `shared/simulator/data/.gitkeep` | Create new |
| — | `shared/simulator/README.md` | Create new |
| — | `base/node-red/flows/opc-ingest.json` | Create new (skeleton) |
| — | `base/opc-client/README.md` | Create new (contract) |
| — | `docker-compose.yml` | Modify (add demo profile) |
| — | `.env.example` | Append simulator vars |

## Files NEVER ported

| Source path | Reason |
|---|---|
| `src/` | ML pipelines — `ml-classical` module is standby |
| `Dockerfile`, `DockerfileETL`, etc. | ML pipeline Dockerfiles — standby |
| `locustfile.py` | References missing Credenciales.txt |
| `entrypoint.sh` | Runtime pip freeze antipattern |
| `fetch_tokens_remote.py` | Offline recovery tool, stays in UCAM |
| `INJECTION_SETUP.md` | Superseded by shared/simulator/README.md |
| `SIMULATION_GUIDE.md` | Superseded by shared/simulator/README.md |
| `docs/openapi.yaml` + renders | Misaligned with code |
| `images/` | Screenshots, not deliverable |
| `system_sizing/` | Potential future separate contribution |
| `deploy/MCT/` | Real client tokens — NEVER |
| `deploy/ESAMUR/` | Real client tokens — NEVER |
| `deploy/t` | 1-char leftover |
| `deploy/ParametrosConfiguracion.txt` | Plaintext admin credentials |
| `deploy/2.2 Manual...docx` | Superseded by deploy/README.md |
| `src/dataloader/Credenciales.txt` | Credentials file — NEVER |
