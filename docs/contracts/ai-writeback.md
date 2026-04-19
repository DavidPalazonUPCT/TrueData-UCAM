# Contrato ML Writeback — `ML → TB`

Contrato HTTP entre el **servicio ML** y **ThingsBoard** (operado por
UCAM) para la escritura de resultados de inferencia como telemetría.

Complementa a [`ml-inference.md`](ml-inference.md) (flujo NR → ML).
Cierra la pregunta abierta 3 de ese documento. Los dos contratos juntos
definen el camino completo inferencia: **NR → ML (inferencia) + ML → TB
(writeback)**.

---

## Resumen del contrato

### Qué ofrece UCAM

- Un **device TB pre-provisionado** (`ml-inference-<cliente>`) con su
  profile asociado `inference_results` y su access token — listo para
  recibir telemetría por REST.
- Una **rule chain asociada al profile** que persiste la telemetría en
  `ts_kv` como cualquier otro device (source of truth).
- **Entrega del token** al servicio ML por canal out-of-band (ver §A6).
- Documentación del endpoint REST y del esquema de campos esperados.

### Qué necesita UCAM del servicio ML

- Un POST HTTP de telemetría por cada resultado de inferencia al
  endpoint TB acordado.
- Cuerpo JSON con el **mismo `ts`** del scan al que corresponde la
  inferencia (clave natural de correlación con los datos raw).
- Manejo local del token (no rotarlo, no exponerlo en logs).
- Colaboración en las preguntas abiertas al final del documento.

---

## Endpoint

```
POST http://<tb-host>:9090/api/v1/<ML_ACCESS_TOKEN>/telemetry
Content-Type: application/json
```

- `<tb-host>` — hostname/IP de ThingsBoard alcanzable desde la red del
  servicio ML. En despliegue típico, `thingsboard` (DNS interno Docker)
  o el host del cluster según entorno.
- `<ML_ACCESS_TOKEN>` — token del device `ml-inference-<cliente>`
  entregado durante el deploy (ver §A6).
- Puerto `9090` — HTTP API de TB.

> **Nota:** la API de TB exige el token en el **path de la URL**, no
> como header. Es una limitación del endpoint HTTP de device de TB CE.
> Evitar logs/traces que capturen la URL completa en claro.

---

## Request body

```json
{
  "ts": 1776326159190,
  "values": {
    "score": 0.847,
    "model_version": "anomaly-detector-v3.1.2",
    "latency_ms": 128,
    "status": "ok"
  }
}
```

### Campos

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `ts` | number (Unix ms) | **Sí** | `sourceTimestamp` del scan original (el mismo que NR envió en el `ts` del body a `/api/inference`). Clave de correlación con la telemetría raw de los sensores |
| `values.score` | number | **Sí** | Output principal del modelo. Rango y semántica los define el equipo ML (probabilidad, anomaly score, clasificación numérica…) |
| `values.model_version` | string | Sí | Identificador de la versión del modelo que produjo el score. Permite auditoría temporal y comparar resultados entre despliegues |
| `values.latency_ms` | number | Sí | Tiempo de inferencia en milisegundos, medido internamente por el servicio ML (desde recepción del POST de NR hasta computar el score) |
| `values.status` | string | Sí | Uno de: `"ok"` \| `"degraded"` \| `"error"`. Permite a dashboards TB distinguir inferencias válidas de las que fallaron parcialmente |
| `values.<extra>` | cualquier tipo TB | No | Campos adicionales que el equipo ML quiera persistir (features derivadas, explicabilidad, flags). TB los almacena como timeseries sin necesidad de declararlos |
| `status` | string | No (default `"ok"`) | `"ok"` si la inferencia se hizo con datos frescos; `"degraded"` si el ML detectó staleness en uno o más sensores vía comparación contra TB raw (mitigación de LIMIT-1 del findings v2). Valor libre para extensiones futuras (`"rejected"`, `"low_confidence"`, etc.) |

### Reglas semánticas

- **Un resultado = un POST**. No batchear varios scans en un solo POST
  (TB acepta arrays en `telemetry` pero rompería la idempotencia por
  `ts` única).
- **`ts` debe coincidir exactamente con el del scan** que NR envió al
  servicio ML. No usar `Date.now()`: rompe la correlación con la
  telemetría raw y anula la idempotencia.
- **Cardinalidad libre en `values`**: el schema anterior es mínimo; se
  pueden añadir keys sin renegociar el contrato.

---

## Ejemplo ejecutable

Simula el POST que el servicio ML hará tras computar la inferencia
para un scan:

```sh
TB_URL="http://localhost:9090"
ML_TOKEN="<token-entregado-durante-deploy>"

curl -s -X POST "${TB_URL}/api/v1/${ML_TOKEN}/telemetry" \
  -H "Content-Type: application/json" \
  -d '{
    "ts": 1776326159190,
    "values": {
      "score": 0.847,
      "model_version": "anomaly-detector-v3.1.2",
      "latency_ms": 128,
      "status": "ok"
    }
  }'
```

Respuesta esperada:

```
HTTP/1.1 200 OK
```

Sin body. TB responde 200 cuando la telemetría se ha aceptado para
persistencia (passa por la rule chain del profile).

Para verificar que se ha almacenado:

```sh
JWT=$(curl -s -X POST "${TB_URL}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"tenant@thingsboard.org","password":"tenant"}' \
    | jq -r .token)

DEVICE_ID=$(curl -s "${TB_URL}/api/tenant/devices?deviceName=ml-inference-<cliente>" \
    -H "X-Authorization: Bearer ${JWT}" | jq -r '.id.id')

curl -s "${TB_URL}/api/plugins/telemetry/DEVICE/${DEVICE_ID}/values/timeseries?keys=score" \
    -H "X-Authorization: Bearer ${JWT}"
```

---

## Respuestas

| Código | Cuerpo | Cuándo |
|---|---|---|
| `200 OK` | vacío | Telemetría aceptada y procesada por la rule chain |
| `401 Unauthorized` | vacío | Token inválido, revocado o expirado |
| `400 Bad Request` | JSON con `message` | Body malformado, `ts` fuera de rango, tipo de dato no soportado |
| `404 Not Found` | vacío | Token existe pero device fue borrado (estado inconsistente) |

> TB no devuelve confirmación de persistencia en la DB (la rule chain
> es async). Un `200` confirma aceptación en el pipeline interno de TB,
> no aterrizaje en el almacén de timeseries. Fallos posteriores se
> observan como ausencia de datos, no como error en la respuesta.

---

## Device + profile pre-provisionados por UCAM

El onboarding de UCAM (`deploy/onboard_client_v2.py`) crea
idempotentemente por cliente:

| Entidad | Nombre | Rol |
|---|---|---|
| Device profile | `inference_results` | Define la rule chain y los CFs para todos los devices de inferencia de la plataforma |
| Device | `ml-inference-<cliente>` | Receptor de writebacks del servicio ML para la planta |
| Access token | (generado por TB) | Credencial que el servicio ML usa en el path de la URL |

El servicio ML **no crea entidades en TB**. Solo POSTea telemetría
usando el token que UCAM le entrega en el onboarding del entorno.

---

## Asunciones explícitas

Estas asunciones son parte del contrato. Si alguna no se cumple,
conviene renegociar antes de integrar.

### A1 — `ts` es el mismo del scan original

El `ts` del writeback es el `sourceTimestamp` que NR envió al servicio
ML en el POST de `/api/inference` (ver [ml-inference.md §Request
body](ml-inference.md)). Esto permite:

- Correlación natural con la telemetría raw en TB: el score del scan
  del instante T se puede unir con los valores de los 27 sensores del
  mismo T, por coincidencia de `ts`.
- Idempotencia: si el servicio ML reintenta un writeback (p.ej. tras
  un timeout transitorio), el mismo `ts` sobrescribe el valor anterior
  sin duplicar.

### A2 — Un scan = un writeback

Cadencia típica **≥34 s** con full scans del PLC; puede ser sub-segundo
cuando llegan CoV events (ver
[ml-inference.md §Reglas semánticas](ml-inference.md) para el detalle
del patrón bimodal). El servicio ML produce un resultado por scan
recibido y escribe un writeback por resultado — cadencia observada de
writebacks igual a la de recepción en `/api/inference`.

Si el modelo soporta inferencia batch (varios scans en una sola
operación), el servicio ML debe desempaquetar el batch en N writebacks
separados, uno por `ts`. No se acepta un array de scores bajo un único
`ts`.

### A3 — Writeback es fire-and-forget

El servicio ML hace el POST y sigue. No hay callback de TB; la
persistencia se verifica por observabilidad (dashboards, queries ad-hoc)
si hay dudas. Los reintentos en caso de fallo transitorio son decisión
del servicio ML; TB es idempotente frente a reintentos con mismo `ts`.

### A4 — Cardinalidad variable no afecta al writeback

La telemetría raw tiene cardinalidad variable por bundle OPC-UA
(1..N tags). El servicio ML decide si genera writeback para cualquier
cardinalidad o solo para bundles completos. Es razonable:

- **Opción estricta:** solo inferir cuando lleguen los N features que
  el modelo espera → no hay writeback para bundles parciales (p.ej.
  un `Heart_Bit` aislado).
- **Opción permisiva:** inferir con lo que llegue imputando features
  faltantes → hay writeback para todo scan recibido, con `status =
  "degraded"` si faltaban features.

UCAM no impone una opción. El contrato solo exige que cada writeback
emitido refleje **fielmente** el estado del modelo para ese `ts`.

### A5 — El servicio ML vive en una red que puede alcanzar a TB

Si el servicio ML está en el mismo compose que TB, usa DNS interno
(`thingsboard:9090`). Si está externo, necesita ruta de red o proxy
hacia el TB de la planta. UCAM no gestiona la conectividad de red del
servicio ML.

### A6 — Entrega y rotación del token out-of-band

El access token del device `ml-inference-<cliente>` se entrega al
equipo ML fuera de este contrato: email con PGP, secret manager del
cliente, fichero `.env` compartido por canal seguro, etc. El token
**no** debe checkearse en ningún repo. El servicio ML lo almacena en
su propia config (variable de entorno, secret manager).

**Política de rotación:**

- UCAM regenera el token invocando `deploy/onboard_client_v2.py
  --force` — la operación rota el token en TB atómicamente, invalida
  el anterior y actualiza los ficheros `.env` locales.
- **Aviso previo:** UCAM notifica al equipo ML por el mismo canal
  out-of-band que se usa para entregar tokens, con mínimo **24 h de
  antelación** salvo que la rotación sea por compromiso confirmado
  (caso urgente: notificación inmediata + token nuevo ya generado).
- **Sin grace period por diseño:** TB revoca el token viejo al
  regenerar. No hay ventana de solapamiento. El equipo ML debe leer
  el nuevo token del `.env` actualizado antes de reanudar writebacks.
- Si el equipo ML detecta `401` en un writeback, debe alertar a UCAM
  (probable rotación no anunciada o token corrupto) y detener
  writebacks hasta recibir token nuevo.

### A7 — Fallo del servicio ML no degrada la telemetría raw

Los caminos NR→TB (telemetría) y NR→ML→TB (inferencia) son
independientes. Si el servicio ML cae, la telemetría raw sigue
llegando a TB sin interrupción. Los scores correspondientes a los
scans mientras ML está caído simplemente no aparecen en el device
`ml-inference-<cliente>`. Ver [ml-inference.md §A5](ml-inference.md).

---

## Casos de error operacionales

| Situación | Comportamiento esperado del servicio ML |
|---|---|
| TB responde `401` | Token revocado/rotado. Log de error crítico, detener writebacks, alertar a UCAM para recibir nuevo token |
| TB responde `404` | Device borrado. Log de error crítico, alertar a UCAM. No intentar recrear — el servicio ML **no** tiene permisos para crear devices |
| TB responde `400` | Bug en el servicio ML (body malformado, tipo incorrecto). Log de error con el body enviado + respuesta de TB. Descartar el writeback, no reintentar |
| TB timeout / 5xx | Reintento con backoff exponencial (recomendado: 3 reintentos, base 1s, max 30s). Tras agotar reintentos, descartar. El scan se considera perdido para inferencia histórica (aunque la raw siguió llegando normalmente) |
| `ts` >> tiempo actual (error en cálculo) | TB lo acepta. Los dashboards lo mostrarán en el futuro. El servicio ML debe tener sanity check antes de enviar |

---

## Preguntas abiertas para el servicio ML

Puntos a alinear antes de pasar a entorno compartido.

1. **Campos adicionales deseados.** ¿El servicio ML querría persistir
   además explainability (SHAP values, feature importances), flags de
   drift, confidence intervals, o metadata del modelo? UCAM puede
   aceptar cualquier key adicional en `values` sin cambios en TB.

2. **Estrategia en bundles parciales** (ver §A4). ¿Inferir siempre
   (imputando) o solo en bundles completos? Decisión del equipo ML;
   documentar en su runbook.

3. **Cadencia máxima.** TB CE tiene los rate limits desactivados por
   default. Si el servicio ML quiere hacer writebacks más frecuentes
   que 1 por scan (p.ej. re-inferencia tras nuevo modelo), ¿qué
   cadencia máxima nos avisa? UCAM configurará rate limits acorde.

4. **Observabilidad.** ¿El servicio ML expone métricas Prometheus
   (latencia, throughput, error rate)? Si sí, UCAM puede scrapearlas
   desde el mismo stack de monitoring que TB/NR.

5. **Entornos.** ¿Dev/pre/prod tienen tokens distintos? Sí por
   defecto, pero confirmar que el servicio ML soporta multi-token en
   su config.

---

## Historial

| Fecha | Autor | Cambio |
|---|---|---|
| 2026-04-16 | David Palazon / Claude | Primera versión — cierra `ml-inference.md` pregunta abierta 3. Device + profile pre-provisionados por UCAM; transport REST con token per-device |
