# Setup end-to-end — Node-RED + ThingsBoard

Checklist para levantar el pipeline v2 desde un repo recién clonado
hasta el primer POST `/api/opc-ingest` validado.

**Pre-requisitos del host:**

- Docker Engine + Docker Compose v2.20+
- `curl`, `jq` (opcional pero recomendado)

---

## 1. Red Docker externa

Una sola vez por host:

```sh
docker network create truedata_iot_network
```

---

## 2. Levantar los servicios

Desde la raíz del repo (levanta TB + Postgres + NR):

```sh
docker compose up -d
```

O levantar cada servicio por separado desde su directorio.

El primer arranque de ThingsBoard tarda ~90 s mientras la DB ejecuta
migraciones de schema.

---

## 3. Esperar a que la API REST de TB responda

```sh
until curl -sf -o /dev/null -X POST http://localhost:9090/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"tenant@thingsboard.org","password":"tenant"}'; do
  sleep 5
done
```

---

## 4. Crear el Gateway device en TB y guardar su access token

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

---

## 5. Configurar el token en Node-RED

El `flows.json` se carga automáticamente desde el bind mount, pero
`flows_cred.json` está cifrado con un `credentialSecret` por instancia
y **no se commitea**. Hay que setear el token a mano:

1. Login en `http://localhost:1880` (usuario `tenant`, password en
   `settings.js`).
2. Editar el config node `TB Gateway` → tab Security →
   `user = $GATEWAY_TOKEN` → Update → Deploy.

---

## 6. Crear el device profile `sensor_planta`

Ver [`../truedata-thingsboard/DEVICE-PROFILE.md`](../truedata-thingsboard/DEVICE-PROFILE.md)
para el procedimiento. El profile debe existir antes del primer scan
para que los devices auto-provisionados hereden la rule chain
correcta.

---

## 7. Validación end-to-end

```sh
curl -s -X POST http://localhost:1880/api/opc-ingest \
    -H "Content-Type: application/json" \
    -d "{\"ts\": $(date +%s%3N), \"values\": {\"POT_CCM\": 42.0}}"
# Esperado: {"status":"ok","tags":1}
```

Verificar que el device `POT_CCM` aparece en TB con profile
`sensor_planta`:

```sh
curl -s "http://localhost:9090/api/tenant/devices?deviceName=POT_CCM" \
    -H "X-Authorization: Bearer $JWT" | jq '{name, type}'
# Esperado: {"name": "POT_CCM", "type": "sensor_planta"}
```

---

## 8. (Opcional) Habilitar la salida ML inference

Por defecto la salida 2 (ML) está silenciada (`flow.ML_INFERENCE_URL`
no set). Para activarla en desarrollo (requiere
`NR_ADMIN_ENABLED=true` en el entorno de NR, ya seteado en
`truedata-nodered/docker-compose.yml`):

```sh
curl -s -X POST http://localhost:1880/admin/set-ml-url \
    -H "Content-Type: application/json" \
    -d '{"url":"http://<ml-host>:<port>/api/inference"}'
```

En producción, `NR_ADMIN_ENABLED` NO debe estar seteado. Los endpoints
`/admin/*` devuelven `404` byte-identical a un path inexistente.
