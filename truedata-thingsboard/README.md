# ThingsBoard — pipeline v2

ThingsBoard es la fuente de verdad del pipeline v2: recibe telemetría
per-device desde Node-RED vía Gateway MQTT API, persiste timeseries, y
expone los datos a consumidores downstream (dashboards, blockchain,
servicios de inferencia).

- **Imagen:** `thingsboard/tb-postgres:4.1.0`
- **DB:** `postgres:13` (sidecar)
- **Contratos de API:** ver
  [`docs/contracts/opc-ingest.md`](../docs/contracts/opc-ingest.md) y
  [`docs/contracts/ml-inference.md`](../docs/contracts/ml-inference.md).
- **Documentación complementaria:** ver
  [`DEVICE-PROFILE.md`](DEVICE-PROFILE.md) para el profile
  `sensor_planta` y su rule chain.

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

## Arrancar

La red Docker externa debe existir previamente (una sola vez):

```sh
docker network create truedata_iot_network
```

Desde este directorio:

```sh
docker compose up -d
```

O desde la raíz del repo, levanta también Node-RED:

```sh
docker compose up -d
```

El primer arranque tarda ~90 s (migraciones de schema PostgreSQL). Si
aparecen errores de permisos sobre volúmenes:

```sh
sudo chmod -R 777 tb-data
sudo chmod 750 tb-data/db
docker compose up -d
```

---

## Credenciales por defecto (dev)

| Rol | Usuario | Password |
|---|---|---|
| System Admin | `sysadmin@thingsboard.org` | `sysadmin` |
| Tenant Admin | `tenant@thingsboard.org` | `tenant` |

| Servicio | Usuario | Password |
|---|---|---|
| PostgreSQL | `thingsboard` | `thingsboard_password` |

> En producción todas estas credenciales deben rotarse en el primer
> arranque. La base de datos persiste en volumen named `postgres-data`.

---

## Health check

```sh
# 1. UI responde
curl -sI http://localhost:9090 | head -1
# Esperado: HTTP/1.1 200 OK (o 302 redirect al login)

# 2. REST API de autenticación
curl -s -X POST http://localhost:9090/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"tenant@thingsboard.org","password":"tenant"}' \
  | jq -r .token | head -c 40
# Esperado: un JWT (~300+ chars)

# 3. Desde Node-RED: DNS + TCP
docker exec truedata-nodered_tb-1 nc -zv thingsboard 1883
docker exec truedata-nodered_tb-1 nc -zv thingsboard 9090
# Esperado: ambos open
```

---

## Envío de telemetría vía Gateway MQTT API (modo v2)

El pipeline v2 usa un único device tipo **Gateway** (`OPC-Gateway`) que
auto-provisiona sub-devices per-sensor cuando Node-RED publica un
`v1/gateway/connect`.

**El Gateway device, sus credenciales y los 4 device profiles
(`sensor_planta`, `inference_input`, `inference_results`,
`blockchain_anchor`) los provisiona `deploy/onboard_client_v2.py`
idempotentemente.** No hay que crearlos a mano:

```sh
export TB_ADMIN_PASSWORD=tenant
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml
```

Tras el onboarding, el token del Gateway queda escrito en
`deploy/secrets/FR_ARAGON/nodered-gateway.env` (mode 0600), que Node-RED
consume vía `env_file:` del compose. Ver
[`truedata-nodered/README.md`](../truedata-nodered/README.md) §Arrancar
para el bring-up end-to-end sin pasos manuales.

Para rotar el token: `python3 deploy/onboard_client_v2.py --force`
(regenera token en TB, actualiza `.env` + `flows_cred.json` cifrado).

---

## Device profiles

El pipeline v2 necesita 4 device profiles en TB. Todos los crea
`deploy/onboard_client_v2.py` al primer run. Ver
[`DEVICE-PROFILE.md`](DEVICE-PROFILE.md) para detalle por profile y la
justificación del naming neutro por cliente.

| Profile | Asignado a | Quién usa el device |
|---|---|---|
| `sensor_planta` | Devices auto-provisionados per-tag (POT_CCM, TURB1, …) | Node-RED (connect + telemetry) |
| `inference_input` | `inference-input` device (1 por cliente, auto-creado por NR) | Snapshot LOCF que se envía a ML — audit trail |
| `inference_results` | `ml-inference-<cliente>` (1 por cliente) | Servicio ML — writeback de scores |
| `blockchain_anchor` | `airtrace-anchor-<cliente>` (1 por cliente) | Servicio airtrace — writeback de evidencias |

---

## Volúmenes persistidos

| Volumen | Contenido |
|---|---|
| `tb-data` | Datos de aplicación de ThingsBoard |
| `tb-logs` | Logs de ThingsBoard |
| `postgres-data` | Base de datos PostgreSQL |

Backup manual: `docker compose down` + `tar czf` sobre los volúmenes.

---

## Logs

```sh
# Logs en vivo de TB
docker compose logs -f thingsboard

# Logs de Postgres (si TB no arranca)
docker logs -f postgres-db

# Logs persistidos en volumen (útiles para post-mortem)
docker exec -it truedata-thingsboard-thingsboard-1 ls /var/log/thingsboard
```

## Troubleshooting

| Problema | Causa probable / mitigación |
|---|---|
| ThingsBoard no arranca | Verificar PostgreSQL: `docker logs postgres-db`. Esperar 90 s en primer arranque |
| Error de permisos en `tb-data/` | `sudo chmod -R 777 tb-data && sudo chmod 750 tb-data/db` |
| Device auto-provisionado sin rule chain | El profile `sensor_planta` no existía cuando llegó el primer `connect`. Re-ejecutar `deploy/onboard_client_v2.py` y reiniciar el flow NR |
| Login falla en la UI | Las credenciales default pueden haberse rotado. Recuperar via SQL en `postgres-db` o recrear el volumen |
| Telemetría no persiste | Confirmar que el device tiene `deviceProfileId` apuntando a un profile con rule chain válida |
