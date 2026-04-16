# Device profile `sensor_planta`

Documento complementario al [`README.md`](README.md) de ThingsBoard.
Describe el único device profile que el pipeline v2 necesita
provisionar y por qué se diseñó con nombre neutro por cliente.

---

## Qué es `sensor_planta`

Un device profile en ThingsBoard agrupa:

- Una **rule chain** asociada (lo que TB ejecuta cuando llega
  telemetría a devices del profile).
- **Calculated fields** del device (si hubiera).
- **Configuración de transporte** (HTTP, MQTT, etc.).
- **Device data schema** (atributos esperados, etc.).

`sensor_planta` encapsula el comportamiento v2 para un sensor genérico
de planta: rule chain que persiste timeseries, dispara alarmas según
thresholds, y expone los datos a consumidores downstream.

---

## Por qué el nombre es neutro (no "Cliente Device")

Decisión de diseño: un profile es **comportamiento**, no identidad del
cliente.

1. Los sensores de una planta tienen el mismo tipo de telemetría, las
   mismas reglas de validación y los mismos thresholds estructurales
   independientemente del operador. Duplicar el profile por cliente
   añade mantenimiento sin ganancia funcional.

2. Si en el futuro se compartiese la instancia TB entre plantas
   (multi-tenant), un profile neutro se reutiliza sin renombrar. Un
   profile con el nombre del cliente obligaría a crear uno nuevo por
   cada cliente.

El identificador del cliente es implícito por el entorno: una
instancia Docker Compose por planta, un TB por compose, un profile
`sensor_planta` en ese TB.

---

## Cómo se crea

El profile debe existir **antes** del primer `v1/gateway/connect` de
Node-RED. Si no existe, TB lo crea automáticamente al recibir el
connect, pero queda **vacío** (sin rule chain, sin calculated fields):
funciona para persistir telemetría básica pero pierde toda la lógica
v2.

### Opción A — Creación from-scratch via REST API

```sh
JWT=$(curl -s -X POST http://localhost:9090/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"tenant@thingsboard.org","password":"tenant"}' \
    | jq -r .token)

curl -s -X POST http://localhost:9090/api/deviceProfile \
    -H "Content-Type: application/json" \
    -H "X-Authorization: Bearer $JWT" \
    -d '{
      "name": "sensor_planta",
      "type": "DEFAULT",
      "transportType": "DEFAULT",
      "provisionType": "DISABLED",
      "description": "Device profile for plant sensors auto-provisioned via Gateway MQTT"
    }'
```

Tras crear el profile, asociar la rule chain deseada desde la UI de TB
(Device profiles → sensor_planta → Rule chain) o vía REST API.

### Opción B — Importar un profile exportado

Si se dispone de un JSON exportado de otra instancia con la rule chain
ya asociada, usar la función de import de la UI de TB (Device profiles
→ Import).

---

## Relación con el campo `type` del payload `connect`

Cuando Node-RED publica:

```json
{"device": "POT_CCM", "type": "sensor_planta"}
```

en el topic `v1/gateway/connect`, TB:

- Si el device `POT_CCM` no existe, lo crea **con profile
  `sensor_planta`**.
- Si el profile `sensor_planta` no existe, lo crea vacío (ver nota
  arriba).
- Si el device ya existe, la operación es idempotente: no se duplica,
  no se cambia el profile.

El campo `type` del topic `v1/gateway/telemetry`, en cambio, **no se
acepta** — telemetría a un device inexistente siempre crea con profile
`default`. Por eso NR emite un `connect` explícito antes del
`telemetry` la primera vez que ve un tag.

---

## Verificación

```sh
# El profile existe
curl -s "http://localhost:9090/api/deviceProfiles?pageSize=100&page=0" \
    -H "X-Authorization: Bearer $JWT" \
    | jq '.data[] | select(.name=="sensor_planta") | {name, id: .id.id}'

# Un device recién auto-provisionado tiene el profile correcto
curl -s "http://localhost:9090/api/tenant/devices?deviceName=POT_CCM" \
    -H "X-Authorization: Bearer $JWT" \
    | jq '{name, type, deviceProfileId: .deviceProfileId.id}'
# Esperado: type = "sensor_planta"
```
