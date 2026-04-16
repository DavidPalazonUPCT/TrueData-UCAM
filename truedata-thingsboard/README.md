# ThingsBoard — TrueData pipeline v2

ThingsBoard es la fuente de verdad del pipeline v2: recibe telemetría
per-device desde Node-RED vía Gateway MQTT API, persiste timeseries, y
expone los datos a consumidores downstream (dashboards, blockchain,
servicios de inferencia).

- **Imagen:** `thingsboard/tb-postgres:4.1.0`
- **DB:** `postgres:13` (sidecar)
- **Contexto:** ver [ADR-001](../docs/architecture/ADR-001-current-pipeline.md)
  para el pipeline original y [ADR-003](../docs/architecture/ADR-003.md)
  para la arquitectura v2.

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

El pipeline v2 usa un único device tipo **Gateway** que auto-provisiona
sub-devices per-sensor. Crear el Gateway device (una sola vez por
entorno):

```sh
JWT=$(curl -s -X POST http://localhost:9090/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"tenant@thingsboard.org","password":"tenant"}' \
    | jq -r .token)

GATEWAY_ID=$(curl -s -X POST http://localhost:9090/api/device \
    -H "Content-Type: application/json" \
    -H "X-Authorization: Bearer $JWT" \
    -d '{"name":"OPC-Gateway","type":"Gateway","additionalInfo":{"gateway":true}}' \
    | jq -r .id.id)

GATEWAY_TOKEN=$(curl -s "http://localhost:9090/api/device/$GATEWAY_ID/credentials" \
    -H "X-Authorization: Bearer $JWT" | jq -r .credentialsId)

echo "Gateway token: $GATEWAY_TOKEN"
```

El `GATEWAY_TOKEN` se configura como credencial del config node
`TB Gateway` en Node-RED (ver
[truedata-nodered/README.md](../truedata-nodered/README.md)).

---

## Device profile `sensor_planta`

Los devices auto-provisionados por Node-RED se adscriben al profile
`sensor_planta` (neutro por cliente). El profile debe crearse antes
del primer `connect` para que la rule chain y los calculated fields
queden asociados correctamente. Ver
[PLAN-001 §D.7](../docs/architecture/PLAN-001) para el razonamiento
y el procedimiento de creación.

---

## Volúmenes persistidos

| Volumen | Contenido |
|---|---|
| `tb-data` | Datos de aplicación de ThingsBoard |
| `tb-logs` | Logs de ThingsBoard |
| `postgres-data` | Base de datos PostgreSQL |

Backup manual: `docker compose down` + `tar czf` sobre los volúmenes.

---

## Troubleshooting

| Problema | Causa probable / mitigación |
|---|---|
| ThingsBoard no arranca | Verificar PostgreSQL: `docker logs postgres-db`. Esperar 90 s en primer arranque |
| Error de permisos en `tb-data/` | `sudo chmod -R 777 tb-data && sudo chmod 750 tb-data/db` |
| Device auto-provisionado sin rule chain | El profile `sensor_planta` no existía cuando llegó el primer `connect`. Crear profile y reiniciar el flow NR |
| Login falla en la UI | Las credenciales default pueden haberse rotado. Recuperar via SQL en `postgres-db` o recrear el volumen |
| Telemetría no persiste | Confirmar que el device tiene `deviceProfileId` apuntando a un profile con rule chain válida |
