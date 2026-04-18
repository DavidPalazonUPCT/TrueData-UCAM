# Device profiles v2

Complemento al [`README.md`](README.md) de ThingsBoard. Describe los
device profiles que el pipeline v2 necesita y cómo se adscriben los
devices a cada uno.

Un device profile en ThingsBoard agrupa:

- Una **rule chain** asociada — lo que TB ejecuta cuando llega
  telemetría a un device del profile.
- **Calculated fields** del device (si los hay).
- **Configuración de transporte** (HTTP, MQTT, …).
- **Device data schema** (atributos esperados).

---

## Resumen

| Profile | Devices adscritos | Quién escribe | Propósito |
|---|---|---|---|
| `sensor_planta` | Uno por tag del PLC (p.ej. `POT_CCM`, `TURB1`…), auto-creados por NR | NR vía Gateway MQTT (`v1/gateway/telemetry`) | Persistir timeseries raw por sensor |
| `inference_input` | `inference-input` (uno único, auto-creado) | NR, paralelo al POST hacia ML | Audit trail: guarda el snapshot LOCF exacto que vio el modelo |
| `inference_results` | `ml-inference-<CLIENT>` (uno por cliente) | Servicio ML, REST `POST /api/v1/<TOKEN>/telemetry` | Writeback de scores, versión del modelo y latencias |
| `blockchain_anchor` | `airtrace-anchor-<CLIENT>` (uno por cliente) | Servicio airtrace, REST | Writeback de evidencias de anclaje en blockchain |

Los 4 profiles los crea `deploy/onboard_client_v2.py` al primer run. Si
un profile no existe cuando llega el primer `connect`, TB lo crea
**vacío** (sin rule chain, sin calculated fields) — la telemetría
persiste pero se pierde toda la lógica asociada. Por eso el onboarding
debe correr **antes** que el primer POST a Node-RED.

---

## `sensor_planta` — sensores del PLC

Profile genérico para todos los sensores de una planta.

### Por qué el nombre es neutro (no `<CLIENTE> Device`)

Un profile es **comportamiento**, no identidad del cliente.

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

### Cómo se adscriben los devices

Node-RED publica en `v1/gateway/connect` con el campo `type`:

```json
{"device": "POT_CCM", "type": "sensor_planta"}
```

TB:

- Si el device `POT_CCM` no existe, lo crea **con profile
  `sensor_planta`**.
- Si el profile `sensor_planta` no existe, lo crea vacío (ver nota
  arriba). Por eso el onboarding tiene que haber corrido antes.
- Si el device ya existe, la operación es idempotente: no se duplica
  ni se cambia el profile.

El campo `type` del topic `v1/gateway/telemetry`, en cambio, **no se
acepta** — telemetría a un device inexistente siempre crea con
profile `default`. Por eso NR emite un `connect` explícito antes del
`telemetry` la primera vez que ve un tag.

---

## `inference_input`, `inference_results`, `blockchain_anchor`

Los tres los crea `onboard_client_v2.py` al primer run. Difieren en
qué device(s) se les asocian:

- `inference_input` → device único `inference-input`, auto-creado por
  NR la primera vez que completa un snapshot LOCF. Contrato interno,
  sin consumidor externo.
- `inference_results` → device `ml-inference-<CLIENT>`, pre-creado
  por el onboarding. Consumido por el servicio ML. Ver contrato en
  [`docs/contracts/ml-writeback.md`](../docs/contracts/ml-writeback.md).
- `blockchain_anchor` → device `airtrace-anchor-<CLIENT>`, pre-creado
  por el onboarding. Consumido por el servicio airtrace. Ver contrato
  en [`docs/contracts/airtrace-writeback.md`](../docs/contracts/airtrace-writeback.md).

Rule chain y calculated fields de cada profile se configuran en la UI
de TB tras el onboarding, o importando un JSON de una instancia
previa (Device profiles → Import).

---

## Verificación

Los 4 profiles existen tras el onboarding:

```sh
JWT=$(curl -s -X POST http://localhost:9090/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"tenant@thingsboard.org","password":"tenant"}' \
    | jq -r .token)

curl -s "http://localhost:9090/api/deviceProfiles?pageSize=100&page=0" \
    -H "X-Authorization: Bearer $JWT" \
    | jq '.data[] | select(.name | test("sensor_planta|inference_input|inference_results|blockchain_anchor")) | .name'
```

Un device recién auto-provisionado tiene el profile esperado:

```sh
curl -s "http://localhost:9090/api/tenant/devices?deviceName=POT_CCM" \
    -H "X-Authorization: Bearer $JWT" \
    | jq '{name, type}'
# Esperado: {"name": "POT_CCM", "type": "sensor_planta"}
```
