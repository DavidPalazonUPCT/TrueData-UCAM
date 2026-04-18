# Contrato Airtrace Writeback — `Airtrace → TB`

Contrato HTTP entre el **servicio airtrace** (anchoring en blockchain)
y **ThingsBoard** (operado por UCAM) para la escritura de evidencias
de anclaje como telemetría.

Complementa a [`ml-inference.md`](ml-inference.md) y
[`ml-writeback.md`](ml-writeback.md). Completa el camino de trazabilidad:
**telemetría raw (sensor) + inferencia (score) + anclaje blockchain
(evidencia)**, los tres indexados por el mismo `ts` del scan original.

> **Nota sobre el alcance:** el path que produce la evidencia (ML →
> airtrace → chain) es responsabilidad de airtrace y está fuera del
> scope UCAM. Este contrato define **solo** cómo airtrace escribe
> evidencia en TB.

---

## Resumen del contrato

### Qué ofrece UCAM

- Un **device TB pre-provisionado** (`airtrace-anchor-<cliente>`) con
  su profile asociado `blockchain_anchor` y su access token.
- Una **rule chain asociada al profile** que persiste la telemetría en
  `ts_kv` sin transformaciones (anchor-as-telemetry).
- **Entrega del token** al equipo airtrace por canal out-of-band.
- Documentación del endpoint REST y del esquema de campos esperados.

### Qué necesita UCAM del servicio airtrace

- Un POST HTTP de telemetría por cada anclaje blockchain al endpoint
  acordado.
- Cuerpo JSON con el **mismo `ts`** del scan al que corresponde el
  anclaje (clave natural de correlación con inferencia y telemetría
  raw).
- Manejo local del token (no rotarlo, no exponerlo en logs).
- Colaboración en las preguntas abiertas al final del documento.

---

## Endpoint

```
POST http://<tb-host>:9090/api/v1/<AIRTRACE_ACCESS_TOKEN>/telemetry
Content-Type: application/json
```

- `<tb-host>` — hostname/IP de ThingsBoard alcanzable desde la red del
  servicio airtrace. Si airtrace está externo al cluster UCAM
  (despliegue típico: servicio hosted en `portal.airtrace.io`), la
  conectividad se resuelve vía dominio público o VPN según el acuerdo
  operativo por cliente.
- `<AIRTRACE_ACCESS_TOKEN>` — token del device `airtrace-anchor-<cliente>`
  entregado durante el deploy.
- Puerto `9090` — HTTP API de TB.

> **Nota de seguridad:** el token viaja en el path de la URL (limitación
> de la API device HTTP de TB CE). En producción con airtrace externo,
> usar HTTPS con certificado válido en el host TB para evitar exponer
> tokens en texto claro.

---

## Request body

```json
{
  "ts": 1776326159190,
  "values": {
    "status": "confirmed",
    "chain_id": "polygon-mainnet",
    "tx_hash": "0x4a7c9e2b8d1f3a6c5e8b9d0f2a3c4e5d6b7a8c9f1e2d3b4a5c6e7f8a9b0c1d2e3",
    "block_number": 52481923,
    "anchor_ts": 1776326175230,
    "payload_digest": "sha256:3b4a5c6e7f8a9b0c1d2e3b4a5c6e7f8a9b0c1d2e3b4a5c6e7f8a9b0c1d2e3b4a"
  }
}
```

### Campos

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `ts` | number (Unix ms) | **Sí** | `sourceTimestamp` del scan original. Idéntico al `ts` del writeback ML correspondiente. Clave de correlación con telemetría raw e inferencia |
| `values.status` | string | **Sí** | Uno de: `"pending"` \| `"confirmed"` \| `"failed"`. Permite a dashboards y auditorías distinguir anclajes efectivos de los que están en espera de confirmación o fallaron |
| `values.chain_id` | string | Sí | Identificador de la chain destino (`"polygon-mainnet"`, `"ethereum-sepolia"`, `"ganache-dev"`, etc.). Hace explícito en qué red vive la evidencia |
| `values.tx_hash` | string (hex) | Sí si `status != pending` | Hash de la transacción. En `pending` puede ser `null` si aún no se ha enviado |
| `values.block_number` | number | Sí si `status == confirmed` | Número del bloque donde se incluyó la transacción. En `pending` / `failed` puede ser `null` |
| `values.anchor_ts` | number (Unix ms) | Sí si `status == confirmed` | Timestamp del bloque (según la chain). Distinto de `ts`: `ts` es cuándo se midió en la planta, `anchor_ts` es cuándo lo confirmó la chain |
| `values.payload_digest` | string | **Sí** | Hash del payload anclado (formato `<algo>:<hex>`, p.ej. `"sha256:..."`). Permite verificación externa: recomputando el digest del dato raw/inferencia y comparando |
| `values.<extra>` | cualquier tipo TB | No | Campos adicionales que el equipo airtrace quiera persistir (gas usado, coste, nonce, URL del explorer, retry count…) |

### Reglas semánticas

- **Un anclaje = un POST por estado**. Ver §A2 para la estrategia de
  estados intermedios (pending → confirmed).
- **`ts` debe coincidir exactamente con el del scan** al que
  corresponde el anclaje. Una evidencia blockchain es **sobre** un
  dato concreto; si `ts` no coincide, la trazabilidad se rompe.
- **`payload_digest` siempre obligatorio**: es el anclaje conceptual
  — lo que prueba que la evidencia blockchain apunta al dato correcto.
  Sin digest, el `tx_hash` es opaco.

---

## Ejemplo ejecutable

Simula los dos POSTs típicos de un anclaje (estado `pending` y luego
`confirmed`):

```sh
TB_URL="http://localhost:9090"
AIRTRACE_TOKEN="<token-entregado-durante-deploy>"
SCAN_TS=1776326159190

# 1) Anclaje en estado pending (tx enviada, aún sin confirmar)
curl -s -X POST "${TB_URL}/api/v1/${AIRTRACE_TOKEN}/telemetry" \
  -H "Content-Type: application/json" \
  -d "{
    \"ts\": ${SCAN_TS},
    \"values\": {
      \"status\": \"pending\",
      \"chain_id\": \"polygon-mainnet\",
      \"tx_hash\": \"0x4a7c9e2b...\",
      \"payload_digest\": \"sha256:3b4a5c6e...\"
    }
  }"

# 2) Anclaje confirmado (tras inclusión en bloque)
curl -s -X POST "${TB_URL}/api/v1/${AIRTRACE_TOKEN}/telemetry" \
  -H "Content-Type: application/json" \
  -d "{
    \"ts\": ${SCAN_TS},
    \"values\": {
      \"status\": \"confirmed\",
      \"chain_id\": \"polygon-mainnet\",
      \"tx_hash\": \"0x4a7c9e2b...\",
      \"block_number\": 52481923,
      \"anchor_ts\": 1776326175230,
      \"payload_digest\": \"sha256:3b4a5c6e...\"
    }
  }"
```

El segundo POST sobrescribe las keys del primero porque comparten `ts`
(idempotencia de TB por `(device, key, ts)`). El estado final queda
como `confirmed` con todos los campos.

Verificación:

```sh
JWT=$(curl -s -X POST "${TB_URL}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"tenant@thingsboard.org","password":"tenant"}' \
    | jq -r .token)

DEVICE_ID=$(curl -s "${TB_URL}/api/tenant/devices?deviceName=airtrace-anchor-<cliente>" \
    -H "X-Authorization: Bearer ${JWT}" | jq -r '.id.id')

curl -s "${TB_URL}/api/plugins/telemetry/DEVICE/${DEVICE_ID}/values/timeseries?keys=status,tx_hash,block_number" \
    -H "X-Authorization: Bearer ${JWT}"
```

---

## Respuestas

| Código | Cuerpo | Cuándo |
|---|---|---|
| `200 OK` | vacío | Telemetría aceptada y procesada por la rule chain |
| `401 Unauthorized` | vacío | Token inválido, revocado o expirado |
| `400 Bad Request` | JSON con `message` | Body malformado, `ts` fuera de rango |
| `404 Not Found` | vacío | Token existe pero device fue borrado |

TB no confirma persistencia en DB (rule chain async). Observar
fallos como ausencia de datos, no como error HTTP.

---

## Device + profile pre-provisionados por UCAM

El onboarding de UCAM (`deploy/onboard_client_v2.py`) crea
idempotentemente por cliente:

| Entidad | Nombre | Rol |
|---|---|---|
| Device profile | `blockchain_anchor` | Define la rule chain y los CFs para todos los devices de anclaje blockchain de la plataforma |
| Device | `airtrace-anchor-<cliente>` | Receptor de writebacks del servicio airtrace para la planta |
| Access token | (generado por TB) | Credencial que airtrace usa en el path de la URL |

El servicio airtrace **no crea entidades en TB**. Solo POSTea
telemetría usando el token que UCAM le entrega en el onboarding.

---

## Asunciones explícitas

Estas asunciones son parte del contrato. Si alguna no se cumple,
conviene renegociar antes de integrar.

### A1 — `ts` es el mismo del scan original

El `ts` del writeback coincide exactamente con el `sourceTimestamp`
del scan en la planta (ver [ml-writeback.md §A1](ml-writeback.md)). La
trazabilidad completa requiere este anclaje temporal: un query por
`ts = T` en TB debe devolver de forma consistente:

- Valores raw de los 27 sensores en el device profile `sensor_planta`
- Score del modelo en `ml-inference-<cliente>`
- Evidencia blockchain en `airtrace-anchor-<cliente>`

Si los tres no comparten `ts`, la trazabilidad se rompe.

### A2 — Estados intermedios vía sobrescritura idempotente

Un anclaje blockchain es async (segundos a minutos según la chain).
Airtrace puede reportar su progreso escribiendo múltiples POSTs con el
mismo `ts` y distintos `status`:

1. `pending` — tx enviada, esperando inclusión en bloque
2. `confirmed` — tx incluida (con `block_number` y `anchor_ts`)
3. O `failed` — si la tx revierte o expira

TB usa `(device, key, ts)` como clave de timeseries: cada POST
sobrescribe las keys anteriores **en ese `ts`**. El estado final del
anclaje es el último POST que airtrace emitió para ese `ts`.

Alternativa: airtrace puede esperar a confirmación antes de postear
(un único POST final). Válido, pero los dashboards UCAM perderán
visibilidad de anclajes en vuelo. La elección queda a airtrace; UCAM
soporta ambas.

### A3 — `payload_digest` es la prueba conceptual del anclaje

Una evidencia blockchain sin `payload_digest` no se puede verificar:
tienes un `tx_hash` en una chain, pero no sabes **qué** se ancló. El
contrato obliga a que airtrace publique el digest del payload que
firmó, de modo que cualquier auditor pueda:

1. Recomputar el digest del dato raw + inferencia del `ts = T` leyendo
   TB.
2. Comparar con `payload_digest` almacenado en
   `airtrace-anchor-<cliente>` para `ts = T`.
3. Verificar que `tx_hash` en la chain `chain_id` contiene ese digest.

Sin los pasos 1-2, el paso 3 es insuficiente.

**Qué cubre el digest (qué se serializa antes de hashear):** airtrace
decide y **documenta** el conjunto. Opciones razonables:

- `sha256(canonical_json({ts, sensors, score, model_version}))` —
  cubre la telemetría que vio el modelo + el resultado.
- `sha256(canonical_json({ts, score}))` — mínimo: solo el resultado.
- `sha256(sha256(raw_telemetry) || sha256(inference))` — Merkle
  ligero si se quieren anclajes verificables por componente.

**Formato serializado:** `<algo>:<hex>` (p.ej. `"sha256:..."`,
`"keccak256:..."`) — el algoritmo viaja junto al hash para evitar
ambigüedad. El valor es la representación hex minúscula del digest
sin prefijo `0x`.

**Requisito de canonicalización:** sea cual sea el input, la
serialización debe ser determinista (JSON canónico con keys ordenadas,
sin espacios opcionales) para que el auditor pueda recomputar desde
los datos en TB y obtener el mismo digest.

### A4 — Anclaje es por scan, no por resultado

La evidencia blockchain corresponde al **scan** (`ts = T`), no a la
inferencia específica. Si el modelo se reentrena y se regenera el
score para `ts = T`, el anclaje original sigue siendo válido para la
telemetría raw, pero sería incorrecto para el nuevo score.

Política por defecto: **re-anclar tras reinferencia**. Airtrace emite
un nuevo anclaje (con el mismo `ts`, pero nuevo `tx_hash` y nuevo
`payload_digest` que incluye el score actualizado). TB sobrescribe la
evidencia antigua.

Alternativa: mantener histórico de anclajes por `ts` usando un
timeseries secundario con array de hashes. Descartado por complejidad.
Si auditorías del pasado importan más que simplicidad, renegociar.

### A5 — Airtrace vive en una red que puede alcanzar a TB

El despliegue típico de airtrace es externo a UCAM (`portal.airtrace.io`
o similar por cliente). La conectividad hacia el TB de cada planta
se resuelve vía dominio público + HTTPS, VPN, o túnel acordado por
cliente. UCAM expone TB al servicio airtrace mediante el mecanismo
operativo acordado; el contrato no lo prescribe.

### A6 — Entrega y rotación del token out-of-band

Política idéntica a [ml-writeback.md §A6](ml-writeback.md):

- Entrega del token de `airtrace-anchor-<cliente>` por canal seguro,
  nunca versionado en repos.
- Rotación vía `deploy/onboard_client_v2.py --force` por parte de
  UCAM, con aviso de al menos 24 h de antelación salvo compromiso
  confirmado (caso urgente: notificación inmediata).
- Sin grace period: el token viejo se invalida al rotar. El equipo
  airtrace debe consumir el nuevo token antes de reanudar writebacks.
- Ante `401`, detener writebacks y alertar a UCAM.

### A7 — Fallos de airtrace no degradan telemetría ni inferencia

Los tres caminos (telemetría, ML, airtrace) son independientes en TB:
cada uno tiene su propio device. Si airtrace cae:

- Telemetría raw sigue llegando (NR → TB vía MQTT Gateway)
- Inferencia sigue computándose y persistiéndose (NR → ML → TB)
- Solo los anclajes de los scans afectados no aparecen en
  `airtrace-anchor-<cliente>`

Cuando airtrace vuelve, puede hacer backfill de scans pendientes
leyendo la timeseries de `ml-inference-<cliente>` vía REST API de TB
y anclando los resultados que falten. Estrategia opcional — airtrace
decide si backfillear o aceptar la pérdida. Ver §pregunta abierta 4.

---

## Casos de error operacionales

| Situación | Comportamiento esperado de airtrace |
|---|---|
| TB responde `401` | Token revocado/rotado. Log de error crítico, detener writebacks, alertar a UCAM |
| TB responde `404` | Device borrado. Log de error crítico, alertar a UCAM |
| TB responde `400` | Bug en airtrace (body malformado). Log + body enviado + respuesta de TB. Descartar, no reintentar |
| TB timeout / 5xx | Reintento con backoff exponencial. Tras agotar reintentos, descartar. El `ts` afectado queda sin evidencia blockchain en TB (pero el tx en chain puede seguir existiendo) |
| Chain confirma tx después de que TB esté down | Reintentar hasta que TB vuelva. La idempotencia por `ts` permite llegar tarde sin duplicar |
| La chain invalida la tx (revert / expiración) | POST con `status: "failed"` en el mismo `ts`. Sobrescribe cualquier `pending` anterior |

---

## Preguntas abiertas para el servicio airtrace

Puntos a alinear antes de pasar a entorno compartido.

1. **Estrategia de estados intermedios** (§A2). ¿Airtrace va a reportar
   `pending` + `confirmed`, o solo el estado final? UCAM soporta ambos
   pero conviene documentar la elección para alinear dashboards.

2. **Política de re-anclaje tras reinferencia** (§A4). ¿Aceptable
   sobrescribir el anclaje en TB cuando el modelo se reentrena, o
   necesitáis histórico de anclajes por `ts`?

3. **Chains soportadas y cadencia de anclaje.** ¿Se ancla cada scan
   (~34 s) o se batchean scans en un solo anclaje? Si se batchea, el
   `payload_digest` cubriría múltiples `ts`; eso requiere un formato
   distinto (array de ts) y se renegocia.

4. **Backfill tras outage** (§A7). ¿Airtrace implementará lectura de
   TB para recuperar scans pendientes de anclaje tras un outage de su
   lado?

5. **Formato del digest.** ¿SHA-256, Keccak-256 (nativo Ethereum),
   SHA-3? Documentar explícitamente el algoritmo que airtrace usa
   para que UCAM pueda verificar.

6. **Exposición de TB a airtrace.** ¿Qué mecanismo de red por cliente
   — HTTPS público con IP allowlist, VPN site-to-site, túnel
   nginx/traefik? Definir por entorno.

---

## Historial

| Fecha | Autor | Cambio |
|---|---|---|
| 2026-04-16 | David Palazon / Claude | Primera versión — cierra el gap de auto-provisioning blockchain. Device + profile pre-provisionados por UCAM; transport REST con token per-device; correlación con ML y telemetría raw vía `ts` compartido |
