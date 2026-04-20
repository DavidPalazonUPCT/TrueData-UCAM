# Contrato AI Writeback — `AI → TB`

Contrato HTTP entre el **servicio AI** y **ThingsBoard** (operado por
la plataforma) para la escritura de resultados de inferencia como
telemetría.

Complementa a [`ai-inference.md`](ai-inference.md) (flujo NR → AI).
Cierra la pregunta abierta 3 de ese documento. Los dos contratos juntos
definen el camino completo inferencia: **NR → AI (inferencia) + AI → TB
(writeback)**.

---

## Resumen del contrato

### Qué ofrece la plataforma

- Un **device TB pre-provisionado** (`ai-inference-<cliente>`) con su
  profile asociado `inference_results` y su access token — listo para
  recibir telemetría por REST.
- Una **rule chain asociada al profile** que persiste la telemetría en
  `ts_kv` como cualquier otro device (source of truth).
- **Entrega del token** al servicio AI por canal out-of-band (ver §A6).
- Documentación del endpoint REST y del esquema de campos esperados.

### Qué necesita la plataforma del servicio AI

- Un POST HTTP de telemetría por cada resultado de inferencia al
  endpoint TB acordado.
- Cuerpo JSON con el **mismo `ts`** del scan al que corresponde la
  inferencia (clave natural de correlación con los datos raw).
- Manejo local del token (no rotarlo, no exponerlo en logs).
- Colaboración en las preguntas abiertas al final del documento.

---

## Endpoint

```
POST http://<tb-host>:9090/api/v1/<AI_ACCESS_TOKEN>/telemetry
Content-Type: application/json
```

- `<tb-host>` — hostname/IP de ThingsBoard alcanzable desde la red del
  servicio AI. En despliegue típico, `thingsboard` (DNS interno Docker)
  o el host del cluster según entorno.
- `<AI_ACCESS_TOKEN>` — token del device `ai-inference-<cliente>`
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
    "status": "ok",
    "alarm_level": 0,
    "alarm_message": null
  }
}
```

### Campos

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `ts` | number (Unix ms) | **Sí** | `sourceTimestamp` del scan original (el mismo que NR envió en el `ts` del body a `/api/inference`). Clave de correlación con la telemetría raw de los sensores |
| `values.score` | number | **Sí** | Output principal del modelo. Rango y semántica los define el equipo AI (probabilidad, anomaly score, clasificación numérica…) |
| `values.model_version` | string | Sí | Identificador de la versión del modelo que produjo el score. Permite auditoría temporal y comparar resultados entre despliegues |
| `values.latency_ms` | number | Sí | Tiempo de inferencia en milisegundos, medido internamente por el servicio AI (desde recepción del POST de NR hasta computar el score) |
| `values.status` | string | Sí | Uno de: `"ok"` \| `"degraded"` \| `"error"`. Distingue inferencias válidas de las que fallaron parcialmente. `"degraded"` indica que el AI detectó staleness en uno o más sensores (comparación contra TB raw). Valor libre para extensiones (`"rejected"`, `"low_confidence"`, …) |
| `values.alarm_level` | number (0-3) | No (default `0`) | Nivel de criticidad derivado de la inferencia. `0` normal · `1` warning · `2` critical · `3` emergency. Alineado con severidades nativas de TB (WARNING / MINOR → MAJOR / CRITICAL). Lo evalúa el equipo AI contra thresholds empíricos del cliente. Ver [`../architecture/alarm-propagation.md`](../architecture/alarm-propagation.md) |
| `values.alarm_message` | string \| null | No | Descripción libre de la alarma para consumo del frontend (p.ej. `"EA_4 fuera de rango histórico 3σ"`). `null` / omitido si `alarm_level == 0` |
| `values.<extra>` | cualquier tipo TB | No | Campos adicionales que el equipo AI quiera persistir (features derivadas, explicabilidad, flags). TB los almacena como timeseries sin necesidad de declararlos |

### Reglas semánticas

- **Un resultado = un POST**. No batchear varios scans en un solo POST
  (TB acepta arrays en `telemetry` pero rompería la idempotencia por
  `ts` única).
- **`ts` debe coincidir exactamente con el del scan** que NR envió al
  servicio AI. No usar `Date.now()`: rompe la correlación con la
  telemetría raw y anula la idempotencia.
- **Cardinalidad libre en `values`**: el schema anterior es mínimo; se
  pueden añadir keys sin renegociar el contrato.
- **Alarmas por inferencia** (`alarm_level`, `alarm_message`): el
  servicio AI decide cuándo emitirlas comparando su `score` contra
  thresholds definidos por el cliente. Son **opcionales** — un
  writeback sin `alarm_level` se interpreta como nivel `0`. No son
  alarmas nativas de TB (rule chain del profile `inference_results`
  puede opcionalmente convertirlas en TB alarms, ver
  [`../architecture/alarm-propagation.md`](../architecture/alarm-propagation.md)).

---

## Ejemplo ejecutable

Simula el POST que el servicio AI hará tras computar la inferencia
para un scan:

```sh
TB_URL="http://localhost:9090"
AI_TOKEN="<token-entregado-durante-deploy>"

curl -s -X POST "${TB_URL}/api/v1/${AI_TOKEN}/telemetry" \
  -H "Content-Type: application/json" \
  -d '{
    "ts": 1776326159190,
    "values": {
      "score": 0.847,
      "model_version": "anomaly-detector-v3.1.2",
      "latency_ms": 128,
      "status": "ok",
      "alarm_level": 2,
      "alarm_message": "EA_4 fuera de rango histórico 3σ"
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

DEVICE_ID=$(curl -s "${TB_URL}/api/tenant/devices?deviceName=ai-inference-<cliente>" \
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

## Device + profile pre-provisionados por la plataforma

El onboarding (`deploy/onboard_client_v2.py`) crea idempotentemente
por cliente:

| Entidad | Nombre | Rol |
|---|---|---|
| Device profile | `inference_results` | Define la rule chain y los CFs para todos los devices de inferencia de la plataforma |
| Device | `ai-inference-<cliente>` | Receptor de writebacks del servicio AI para la planta |
| Access token | (generado por TB) | Credencial que el servicio AI usa en el path de la URL |

El servicio AI **no crea entidades en TB**. Solo POSTea telemetría
usando el token que la plataforma le entrega en el onboarding del
entorno.

---

## Asunciones explícitas

Estas asunciones son parte del contrato. Si alguna no se cumple,
conviene renegociar antes de integrar.

### A1 — `ts` es el mismo del scan original

El `ts` del writeback es el `sourceTimestamp` que NR envió al servicio
AI en el POST de `/api/inference` (ver [ai-inference.md §Request
body](ai-inference.md)). Esto permite:

- Correlación natural con la telemetría raw en TB: el score del scan
  del instante T se puede unir con los valores de los 27 sensores del
  mismo T, por coincidencia de `ts`.
- Idempotencia: si el servicio AI reintenta un writeback (p.ej. tras
  un timeout transitorio), el mismo `ts` sobrescribe el valor anterior
  sin duplicar.

### A2 — Un scan = un writeback

Cadencia típica **≥34 s** con full scans del PLC; puede ser sub-segundo
cuando llegan CoV events (ver
[ai-inference.md §Reglas semánticas](ai-inference.md) para el detalle
del patrón bimodal). El servicio AI produce un resultado por scan
recibido y escribe un writeback por resultado — cadencia observada de
writebacks igual a la de recepción en `/api/inference`.

Si el modelo soporta inferencia batch (varios scans en una sola
operación), el servicio AI debe desempaquetar el batch en N writebacks
separados, uno por `ts`. No se acepta un array de scores bajo un único
`ts`.

### A3 — Writeback es fire-and-forget

El servicio AI hace el POST y sigue. No hay callback de TB; la
persistencia se verifica por observabilidad (dashboards, queries ad-hoc)
si hay dudas. Los reintentos en caso de fallo transitorio son decisión
del servicio AI; TB es idempotente frente a reintentos con mismo `ts`.

### A4 — Cardinalidad variable no afecta al writeback

La telemetría raw tiene cardinalidad variable por bundle OPC-UA
(1..N tags). El servicio AI decide si genera writeback para cualquier
cardinalidad o solo para bundles completos. Es razonable:

- **Opción estricta:** solo inferir cuando lleguen los N features que
  el modelo espera → no hay writeback para bundles parciales (p.ej.
  un `Heart_Bit` aislado).
- **Opción permisiva:** inferir con lo que llegue imputando features
  faltantes → hay writeback para todo scan recibido, con `status =
  "degraded"` si faltaban features.

La plataforma no impone una opción. El contrato solo exige que cada
writeback emitido refleje **fielmente** el estado del modelo para ese
`ts`.

### A5 — El servicio AI vive en una red que puede alcanzar a TB

Si el servicio AI está en el mismo compose que TB, usa DNS interno
(`thingsboard:9090`). Si está externo, necesita ruta de red o proxy
hacia el TB de la planta. La plataforma no gestiona la conectividad de
red del servicio AI.

### A6 — Entrega y rotación del token out-of-band

El access token del device `ai-inference-<cliente>` se entrega al
equipo AI **vía fichero `.env` generado por el onboarding de la
plataforma** y consumido por Docker compose. El mecanismo completo
(ruta, shape, arranque ordenado, smoke test unilateral, troubleshooting)
está formalizado en
[`secrets-delivery.md`](secrets-delivery.md).

Resumen: `base/deploy/secrets/<CLIENT>/ai-inference.env` expone
`CLIENT`, `TB_HOST`, `TB_DEVICE_NAME`, `TB_DEVICE_TOKEN`. El servicio AI
lo carga con `env_file:` en su `docker-compose.yml`. El token **no**
debe checkearse en ningún repo (el fichero está gitignored en `base/`
por diseño).

**Política de rotación:**

- La plataforma regenera el token invocando `deploy/onboard_client_v2.py
  --force` — la operación rota el token en TB atómicamente, invalida
  el anterior y actualiza los ficheros `.env` locales.
- **Aviso previo:** la plataforma notifica al equipo AI por el mismo
  canal out-of-band que se usa para entregar tokens, con mínimo **24 h
  de antelación** salvo que la rotación sea por compromiso confirmado
  (caso urgente: notificación inmediata + token nuevo ya generado).
- **Sin grace period por diseño:** TB revoca el token viejo al
  regenerar. No hay ventana de solapamiento. El equipo AI debe leer
  el nuevo token del `.env` actualizado antes de reanudar writebacks.
- Si el equipo AI detecta `401` en un writeback, debe alertar a la
  plataforma (probable rotación no anunciada o token corrupto) y
  detener writebacks hasta recibir token nuevo.

### A7 — Fallo del servicio AI no degrada la telemetría raw

Los caminos NR→TB (telemetría) y NR→AI→TB (inferencia) son
independientes. Si el servicio AI cae, la telemetría raw sigue
llegando a TB sin interrupción. Los scores correspondientes a los
scans mientras AI está caído simplemente no aparecen en el device
`ai-inference-<cliente>`. Ver [ai-inference.md §A5](ai-inference.md).

---

## Casos de error operacionales

| Situación | Comportamiento esperado del servicio AI |
|---|---|
| TB responde `401` | Token revocado/rotado. Log de error crítico, detener writebacks, alertar a la plataforma para recibir nuevo token |
| TB responde `404` | Device borrado. Log de error crítico, alertar a la plataforma. No intentar recrear — el servicio AI **no** tiene permisos para crear devices |
| TB responde `400` | Bug en el servicio AI (body malformado, tipo incorrecto). Log de error con el body enviado + respuesta de TB. Descartar el writeback, no reintentar |
| TB timeout / 5xx | Reintento con backoff exponencial (recomendado: 3 reintentos, base 1s, max 30s). Tras agotar reintentos, descartar. El scan se considera perdido para inferencia histórica (aunque la raw siguió llegando normalmente) |
| `ts` >> tiempo actual (error en cálculo) | TB lo acepta. Los dashboards lo mostrarán en el futuro. El servicio AI debe tener sanity check antes de enviar |

---

## Preguntas abiertas para el servicio AI

Puntos a alinear antes de pasar a entorno compartido.

1. **Campos adicionales deseados.** ¿El servicio AI querría persistir
   además explainability (SHAP values, feature importances), flags de
   drift, confidence intervals, o metadata del modelo? La plataforma
   puede aceptar cualquier key adicional en `values` sin cambios en TB.

2. **Estrategia en bundles parciales** (ver §A4). ¿Inferir siempre
   (imputando) o solo en bundles completos? Decisión del equipo AI;
   documentar en su runbook.

3. **Cadencia máxima.** TB CE tiene los rate limits desactivados por
   default. Si el servicio AI quiere hacer writebacks más frecuentes
   que 1 por scan (p.ej. re-inferencia tras nuevo modelo), ¿qué
   cadencia máxima nos avisa? La plataforma configurará rate limits
   acorde.

4. **Observabilidad.** ¿El servicio AI expone métricas Prometheus
   (latencia, throughput, error rate)? Si sí, la plataforma puede
   scrapearlas desde el mismo stack de monitoring que TB/NR.

5. **Entornos.** ¿Dev/pre/prod tienen tokens distintos? Sí por
   defecto, pero confirmar que el servicio AI soporta multi-token en
   su config.

---

## Historial

| Fecha | Autor | Cambio |
|---|---|---|
| 2026-04-16 | David Palazon / Claude | Primera versión — cierra `ai-inference.md` pregunta abierta 3. Device + profile pre-provisionados por la plataforma; transport REST con token per-device |
