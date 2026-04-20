# Contrato Blockchain — `AI → Blockchain → TB`

Dos contratos complementarios del servicio blockchain:

1. **Trigger (AI → Blockchain):** cómo recibe los scans a anclar.
2. **Writeback (Blockchain → TB):** cómo escribe la evidencia en TB.

Complementa a [`ai-service.md`](ai-service.md). El pipeline completo de
trazabilidad — telemetría raw + inferencia + anclaje blockchain — usa el
mismo `ts` del scan original como clave de correlación en las tres capas.

---

## Trigger — AI hace push al servicio blockchain

**Patrón: fire-and-forget HTTP**, idéntico al NR→AI. El servicio AI
computa el score y, si tiene la env var `BLOCKCHAIN_ANCHOR_URL` set,
POSTea el payload al servicio blockchain en paralelo al writeback a TB.
Si la env var está unset, el push se omite silenciosamente.

```
POST ${BLOCKCHAIN_ANCHOR_URL}     # típico: http://blockchain:6000/api/anchor
Content-Type: application/json

{
  "ts": 1776326159190,
  "sensors": {"POT_CCM": 300.0, ...},     // snapshot LOCF que el AI recibió
  "score": 0.847,                          // output del modelo
  "model_version": "anomaly-detector-v3.1.2",
  "latency_ms": 128,
  "status": "ok"                           // "ok" | "degraded" | "error"
}
```

### Contrato del body

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `ts` | number (Unix ms) | Sí | `sourceTimestamp` del scan. Misma clave que inferencia y telemetría raw en TB |
| `sensors` | object | Sí | Snapshot LOCF tal como lo recibió el AI (cardinalidad fija N = EXPECTED_TAGS) |
| `score` | number | Sí | Output del modelo. Necesario para computar `payload_digest` |
| `model_version` | string | Sí | Versión del modelo. Parte de la evidencia auditable |
| `latency_ms` | number | No | Tiempo de inferencia. Útil para auditoría pero no va a la cadena |
| `status` | string | No (default `"ok"`) | Si `"error"`, el blockchain puede decidir no anclar |

### Semántica y fallback

- **Fire-and-forget**: el AI no espera confirmación. Timeout 5 s.
- **Response ignorada**: 2xx/4xx/5xx indistinto — el AI solo quiere
  asegurarse de que la petición salió. Reliability la maneja el
  servicio blockchain (queue local, retry on-chain, etc.).
- **Resiliencia**: si el blockchain service está caído, el AI lo nota
  por timeout o connection refused, lo loguea (`[warn] blockchain push
  failed: <err>`) y continúa. La inferencia ya fue escrita a TB en
  paralelo — no se pierde data raw ni score.
- **`BLOCKCHAIN_ANCHOR_URL` unset**: el AI omite el push (blockchain
  opcional por cliente / por entorno). Ningún warning; comportamiento
  by-design para dev local.

### Responsabilidad del servicio blockchain

- **Reliability** ante fallos de cadena: queue persistente local,
  reintento con backoff, dead-letter para evidencias no ancables.
- **Idempotencia por `ts`**: si recibe dos pushes con el mismo `ts`
  (p.ej. rerun del AI tras crash), debe tratar el segundo como no-op o
  como re-anclaje explícito según su política.
- **Fuente del digest**: puede re-leer el device `inference-input` de TB
  para computar un `payload_digest` auditable a partir del snapshot
  original (ver `ai-service.md §A8`), o usar directamente el `sensors`
  del body.

---

> **Scope boundary:** el path `AI → blockchain → chain` y la reliability
> interna del servicio blockchain están **fuera** del scope de la
> plataforma `base/`. Este contrato define cómo AI invoca a blockchain
> (arriba) y cómo blockchain escribe evidencia a TB (abajo).

---

## Writeback — Blockchain → TB

## Resumen del contrato

### Qué ofrece la plataforma

- Un **device TB pre-provisionado** (`blockchain-anchor-<cliente>`) con
  su profile asociado `blockchain_anchor` y su access token.
- Una **rule chain asociada al profile** que persiste la telemetría en
  `ts_kv` sin transformaciones (anchor-as-telemetry).
- **Entrega del token** al equipo del servicio blockchain por canal
  out-of-band.
- Documentación del endpoint REST y del esquema de campos esperados.

### Qué necesita la plataforma del servicio blockchain

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
POST http://<tb-host>:9090/api/v1/<BLOCKCHAIN_ACCESS_TOKEN>/telemetry
Content-Type: application/json
```

- `<tb-host>` — hostname/IP de ThingsBoard alcanzable desde la red del
  servicio blockchain. Si el servicio blockchain está externo al cluster
  de la plataforma (despliegue típico: servicio hosted externo), la
  conectividad se resuelve vía dominio público o VPN según el acuerdo
  operativo por cliente.
- `<BLOCKCHAIN_ACCESS_TOKEN>` — token del device
  `blockchain-anchor-<cliente>` entregado durante el deploy.
- Puerto `9090` — HTTP API de TB.

> **Nota de seguridad:** el token viaja en el path de la URL (limitación
> de la API device HTTP de TB CE). En producción con servicio blockchain
> externo, usar HTTPS con certificado válido en el host TB para evitar
> exponer tokens en texto claro.

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
| `ts` | number (Unix ms) | **Sí** | `sourceTimestamp` del scan original. Idéntico al `ts` del writeback AI correspondiente. Clave de correlación con telemetría raw e inferencia |
| `values.status` | string | **Sí** | Uno de: `"pending"` \| `"confirmed"` \| `"failed"`. Permite a dashboards y auditorías distinguir anclajes efectivos de los que están en espera de confirmación o fallaron |
| `values.chain_id` | string | Sí | Identificador de la chain destino (`"polygon-mainnet"`, `"ethereum-sepolia"`, `"ganache-dev"`, etc.). Hace explícito en qué red vive la evidencia |
| `values.tx_hash` | string (hex) | Sí si `status != pending` | Hash de la transacción. En `pending` puede ser `null` si aún no se ha enviado |
| `values.block_number` | number | Sí si `status == confirmed` | Número del bloque donde se incluyó la transacción. En `pending` / `failed` puede ser `null` |
| `values.anchor_ts` | number (Unix ms) | Sí si `status == confirmed` | Timestamp del bloque (según la chain). Distinto de `ts`: `ts` es cuándo se midió en la planta, `anchor_ts` es cuándo lo confirmó la chain |
| `values.payload_digest` | string | **Sí** | Hash del payload anclado (formato `<algo>:<hex>`, p.ej. `"sha256:..."`). Permite verificación externa: recomputando el digest del dato raw/inferencia y comparando |
| `values.<extra>` | cualquier tipo TB | No | Campos adicionales que el equipo del servicio blockchain quiera persistir (gas usado, coste, nonce, URL del explorer, retry count…) |

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
BLOCKCHAIN_TOKEN="<token-entregado-durante-deploy>"
SCAN_TS=1776326159190

# 1) Anclaje en estado pending (tx enviada, aún sin confirmar)
curl -s -X POST "${TB_URL}/api/v1/${BLOCKCHAIN_TOKEN}/telemetry" \
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
curl -s -X POST "${TB_URL}/api/v1/${BLOCKCHAIN_TOKEN}/telemetry" \
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

DEVICE_ID=$(curl -s "${TB_URL}/api/tenant/devices?deviceName=blockchain-anchor-<cliente>" \
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

## Device + profile pre-provisionados por la plataforma

El onboarding (`python3 -m deploy.onboarding`) crea idempotentemente
por cliente:

| Entidad | Nombre | Rol |
|---|---|---|
| Device profile | `blockchain_anchor` | Define la rule chain y los CFs para todos los devices de anclaje blockchain de la plataforma |
| Device | `blockchain-anchor-<cliente>` | Receptor de writebacks del servicio blockchain para la planta |
| Access token | (generado por TB) | Credencial que el servicio blockchain usa en el path de la URL |

El servicio blockchain **no crea entidades en TB**. Solo POSTea
telemetría usando el token que la plataforma le entrega en el
onboarding.

---

## Asunciones explícitas

Estas asunciones son parte del contrato. Si alguna no se cumple,
conviene renegociar antes de integrar.

### A1 — `ts` es el mismo del scan original

El `ts` del writeback coincide exactamente con el `sourceTimestamp`
del scan en la planta (ver [ai-service.md §A1](ai-service.md)). La
trazabilidad completa requiere este anclaje temporal: un query por
`ts = T` en TB debe devolver de forma consistente:

- Valores raw de los 27 sensores en el device profile `sensor_planta`
- Score del modelo en `ai-inference-<cliente>`
- Evidencia blockchain en `blockchain-anchor-<cliente>`

Si los tres no comparten `ts`, la trazabilidad se rompe.

### A2 — Estados intermedios vía sobrescritura idempotente

Un anclaje blockchain es async (segundos a minutos según la chain).
El servicio blockchain puede reportar su progreso escribiendo múltiples
POSTs con el mismo `ts` y distintos `status`:

1. `pending` — tx enviada, esperando inclusión en bloque
2. `confirmed` — tx incluida (con `block_number` y `anchor_ts`)
3. O `failed` — si la tx revierte o expira

TB usa `(device, key, ts)` como clave de timeseries: cada POST
sobrescribe las keys anteriores **en ese `ts`**. El estado final del
anclaje es el último POST que el servicio blockchain emitió para ese
`ts`.

Alternativa: el servicio blockchain puede esperar a confirmación antes
de postear (un único POST final). Válido, pero los dashboards de la
plataforma perderán visibilidad de anclajes en vuelo. La elección queda
al servicio blockchain; la plataforma soporta ambas.

### A3 — `payload_digest` es la prueba conceptual del anclaje

Una evidencia blockchain sin `payload_digest` no se puede verificar:
tienes un `tx_hash` en una chain, pero no sabes **qué** se ancló. El
contrato obliga a que el servicio blockchain publique el digest del
payload que firmó, de modo que cualquier auditor pueda:

1. Recomputar el digest del dato raw + inferencia del `ts = T` leyendo
   TB.
2. Comparar con `payload_digest` almacenado en
   `blockchain-anchor-<cliente>` para `ts = T`.
3. Verificar que `tx_hash` en la chain `chain_id` contiene ese digest.

Sin los pasos 1-2, el paso 3 es insuficiente.

**Qué cubre el digest (qué se serializa antes de hashear):** el servicio
blockchain decide y **documenta** el conjunto. Opciones razonables:

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

Política por defecto: **re-anclar tras reinferencia**. El servicio
blockchain emite un nuevo anclaje (con el mismo `ts`, pero nuevo
`tx_hash` y nuevo `payload_digest` que incluye el score actualizado).
TB sobrescribe la evidencia antigua.

Alternativa: mantener histórico de anclajes por `ts` usando un
timeseries secundario con array de hashes. Descartado por complejidad.
Si auditorías del pasado importan más que simplicidad, renegociar.

### A5 — El servicio blockchain vive en una red que puede alcanzar a TB

El despliegue típico del servicio blockchain es externo a la plataforma
Base (servicio hosted externo por cliente). La conectividad hacia el TB
de cada planta se resuelve vía dominio público + HTTPS, VPN, o túnel
acordado por cliente. La plataforma expone TB al servicio blockchain
mediante el mecanismo operativo acordado; el contrato no lo prescribe.

### A6 — Entrega y rotación del token

Mecanismo completo (shape del `.env`, consumo vía Docker `env_file:`,
política de rotación, recovery tras `401`, troubleshooting) en
**[`secrets-delivery.md`](secrets-delivery.md)** — único doc, aplica
igual para AI y blockchain.

Para el servicio blockchain, el fichero relevante es
`base/deploy/secrets/<CLIENT>/blockchain-anchor.env`.

### A7 — Fallos del servicio blockchain no degradan telemetría ni inferencia

Los tres caminos (telemetría, AI, blockchain) son independientes en TB:
cada uno tiene su propio device. Si el servicio blockchain cae:

- Telemetría raw sigue llegando (NR → TB vía MQTT Gateway)
- Inferencia sigue computándose y persistiéndose (NR → AI → TB)
- Solo los anclajes de los scans afectados no aparecen en
  `blockchain-anchor-<cliente>`

Cuando el servicio blockchain vuelve, puede hacer backfill de scans
pendientes leyendo la timeseries de `ai-inference-<cliente>` vía REST
API de TB y anclando los resultados que falten. Estrategia opcional —
el servicio blockchain decide si backfillear o aceptar la pérdida.
Ver §pregunta abierta 4.

---

## Casos de error operacionales

| Situación | Comportamiento esperado del servicio blockchain |
|---|---|
| TB responde `401` | Token revocado/rotado. Log de error crítico, detener writebacks, alertar a la plataforma |
| TB responde `404` | Device borrado. Log de error crítico, alertar a la plataforma |
| TB responde `400` | Bug en el servicio blockchain (body malformado). Log + body enviado + respuesta de TB. Descartar, no reintentar |
| TB timeout / 5xx | Reintento con backoff exponencial. Tras agotar reintentos, descartar. El `ts` afectado queda sin evidencia blockchain en TB (pero el tx en chain puede seguir existiendo) |
| Chain confirma tx después de que TB esté down | Reintentar hasta que TB vuelva. La idempotencia por `ts` permite llegar tarde sin duplicar |
| La chain invalida la tx (revert / expiración) | POST con `status: "failed"` en el mismo `ts`. Sobrescribe cualquier `pending` anterior |

---

## Preguntas abiertas para el servicio blockchain

Puntos a alinear antes de pasar a entorno compartido.

1. **Estrategia de estados intermedios** (§A2). ¿El servicio blockchain
   va a reportar `pending` + `confirmed`, o solo el estado final? La
   plataforma soporta ambos pero conviene documentar la elección para
   alinear dashboards.

2. **Política de re-anclaje tras reinferencia** (§A4). ¿Aceptable
   sobrescribir el anclaje en TB cuando el modelo se reentrena, o
   necesitáis histórico de anclajes por `ts`?

3. **Chains soportadas y cadencia de anclaje.** ¿Se ancla cada scan
   (~34 s) o se batchean scans en un solo anclaje? Si se batchea, el
   `payload_digest` cubriría múltiples `ts`; eso requiere un formato
   distinto (array de ts) y se renegocia.

4. **Backfill tras outage** (§A7). ¿El servicio blockchain implementará
   lectura de TB para recuperar scans pendientes de anclaje tras un
   outage de su lado?

5. **Formato del digest.** ¿SHA-256, Keccak-256 (nativo Ethereum),
   SHA-3? Documentar explícitamente el algoritmo que el servicio
   blockchain usa para que la plataforma pueda verificar.

6. **Exposición de TB al servicio blockchain.** ¿Qué mecanismo de red
   por cliente — HTTPS público con IP allowlist, VPN site-to-site,
   túnel nginx/traefik? Definir por entorno.

---

## Historial

| Fecha | Autor | Cambio |
|---|---|---|
| 2026-04-16 | David Palazon / Claude | Primera versión — cierra el gap de auto-provisioning blockchain. Device + profile pre-provisionados por la plataforma; transport REST con token per-device; correlación con AI y telemetría raw vía `ts` compartido |
| 2026-04-20 | David Palazon / Claude | Añadida sección §Trigger formalizando el push AI→Blockchain (fire-and-forget HTTP, simétrico al NR→AI). Cierra la pregunta crítica levantada por el review de docs: el servicio blockchain recibe los scans vía push del AI, no por pull de TB ni subscripción MQTT |
