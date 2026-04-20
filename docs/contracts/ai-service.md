# Contrato AI Service — NR ↔ AI ↔ TB

Contrato completo del **servicio AI** en el pipeline TrueData v2: el servicio
recibe peticiones de inferencia desde Node-RED, produce un resultado, y escribe
ese resultado de vuelta a ThingsBoard como telemetría del device
`ai-inference-<cliente>`.

Este documento es la referencia de implementación para el equipo que desarrolla
y opera el servicio AI. Cubre el camino completo:

- **Parte 1 — Inferencia (NR → AI):** qué envía Node-RED al servicio AI en cada
  scan del PLC, y qué necesita NR del servicio AI para funcionar.
- **Parte 2 — Writeback (AI → TB):** cómo escribe el servicio AI sus resultados
  en ThingsBoard, y qué garantiza la plataforma para habilitarlo.

---

## Parte 1 — Inferencia (NR → AI)

### Qué ofrece Node-RED

- Un `POST` HTTP por cada scan del PLC al endpoint del servicio AI,
  emitido en paralelo a la persistencia en ThingsBoard.
- Un body JSON compacto con el timestamp del scan y todas las lecturas
  (`{ts, sensors}`), sin pre-procesado ni filtrado.
- Despacho independiente: la disponibilidad y latencia del servicio AI
  no afectan a la persistencia en ThingsBoard ni al acuse al servicio OPC.
- El scan completo queda persistido en ThingsBoard vía el otro camino
  del pipeline, disponible por REST API como fuente de verdad para backfill.

### Qué necesita Node-RED del servicio AI

- Un endpoint HTTP accesible que acepte POST con `Content-Type: application/json`.
- Respuesta (cualquiera, 2xx/4xx/5xx) en menos de 5 s en condiciones normales.
  Node-RED corta cualquier petición que exceda ese timeout.
- Que el servicio AI sea autónomo en el writeback de resultados a TB
  (Node-RED no participa en ese camino — ver Parte 2).

### Endpoint

```
POST http://<ai-host>:<ai-port>/<ai-path>
Content-Type: application/json
```

La URL completa se configura en Node-RED en tiempo de despliegue vía
`ai_inference_url` en `truedata-nodered/data/runtime_config.json`.
El path exacto (`/api/inference` u otro) se acuerda entre equipos; lo
relevante es que coincida con lo configurado en Node-RED.

### Request body

```json
{
  "ts": 1776326159190,
  "sensors": {
    "POT_CCM": 300.0,
    "TURB1": 0.0,
    "FT1": 1322.22,
    "pH_Entrada": 7.635,
    "SH2_AguaBruta": 3.472,
    "reserva4": 81.71
  }
}
```

#### Campos

| Campo | Tipo | Descripción |
|---|---|---|
| `ts` | number (Unix ms) | Instante wall-clock en el que NR construyó el frame (`Date.now()` en el tick que lo emitió). No es el `ts` del PLC; el frame es un contrato de interfaz entre NR y el AI, no una fotografía física síncrona de la planta |
| `sensors` | object | Diccionario `{tag_name: value}` con **cardinalidad fija N** = `EXPECTED_TAGS` configurados en NR (27 para FR_ARAGON; futuros clientes pueden tener otro N). Construido por Node-RED vía **carry-forward** sobre el estado `lastSeen` |
| `sensors.<tag>` | number \| boolean \| string | Último valor conocido (LOCF) para ese tag. Puede venir de un scan OPC acabado de llegar o de uno anterior — NR no diferencia |

### Reglas semánticas

- **Cadencia periódica wall-clock**, desacoplada del patrón de publicación OPC.
  NR emite al servicio AI **cada `inference_emit_interval_ms`** (default `40000`
  ms; configurable en `runtime_config.json`). El servicio AI ve un ritmo
  constante independiente de si el PLC acaba de publicar un full scan o un CoV
  parcial. Esta decisión elimina el aliasing temporal del diseño event-driven
  anterior y desacopla el batch rate del modelo del ciclo del PLC. Justificación
  en mediciones sobre FR_ARAGON (722h dump): T=40 s sigue el mismo ratio de
  cobertura que T=60 s (baja redundancia) con mayor frecuencia de inferencia.
- **Frame como contrato de interfaz, no como foto física.** El `sensors` es
  la representación LOCF agregada que consume el servicio aguas abajo. La
  coherencia temporal interna entre tags (si todos corresponden al mismo scan
  PLC) es responsabilidad del modelo, no de NR.
- **Cardinalidad fija `|sensors| = N`.** `N = |EXPECTED_TAGS|` por cliente.
  Nunca varía. Los tags que no aparezcan en el último scan se rellenan con su
  valor LOCF. Si el bundle trae tags adicionales (nuevos sensores en campo),
  NR los persiste en TB raw pero **no los añade al payload AI** — requieren
  rebootstrap del modelo con nuevo `EXPECTED_TAGS`.
- **Los nombres de tags son literales del PLC** (no normalizados).
- **Warm-up gate.** Si algún `EXPECTED_TAGS` no ha aparecido nunca en
  `lastSeen`, NR omite el frame. El warmup acaba cuando los N tags se han
  visto al menos una vez; no hay timeout explícito. Ver §A7.

#### Garantías sobre el campo `sensors`

- **Nunca contiene `null` ni `undefined`.** NR filtra valores nulos al
  actualizar su state LOCF; el snapshot siempre trae valores reales del último
  scan válido por tag.
- **Contiene exactamente los tags de `EXPECTED_TAGS`.** Tags fuera del set no
  entran al snapshot (sí persisten en TB raw por separado).
- **No hay garantía de freshness por tag.** Un tag que dejó de publicar su
  valor en campo mantiene indefinidamente su última lectura en el frame (LOCF
  sin TTL). La detección de "sensor muerto" queda delegada al servicio AI,
  que puede correlacionar el `sensors[tag]` con el `ts` del último punto de ese
  sensor en TB raw si lo requiere.

#### Estabilidad del tipo de valor

NR no valida el tipo del valor de cada tag. El mismo `sensors[tag]` puede ser
`float` en una inferencia y `string` en la siguiente si el PLC cambia el tipo
de la variable subyacente. El AI debe hacer sanity-check de tipos en su preproc
(p.ej. `isinstance(v, (int, float))`) y rutar a un fallback si el tipo no es el
esperado.

### Ejemplo ejecutable

Simulando la llegada de un scan al servicio AI:

```sh
curl -s -X POST http://localhost:5000/api/inference \
  -H "Content-Type: application/json" \
  -d '{
    "ts": 1776326159190,
    "sensors": {
      "POT_CCM": 300.0,
      "TURB1": 0.0,
      "FT1": 1322.22
    }
  }'
```

### Comportamiento de Node-RED hacia el servicio AI

Node-RED actúa como **disparador periódico**, no como consumidor del resultado:

| Aspecto | Comportamiento |
|---|---|
| Procesamiento de la respuesta | NR **descarta** el body y el código. Cualquier 2xx/4xx/5xx se loguea para observabilidad y se ignora funcionalmente |
| Timeout | **5000 ms**. Si el servicio AI no responde en 5 s, NR cancela la conexión. El siguiente tick llega `inference_emit_interval_ms` después (default 40 s) |
| Reintentos | Ninguno. Un POST fallido (timeout, error de red, 5xx) no se reenvía. El siguiente tick construye un frame fresco desde LOCF |
| Concurrencia | Máximo un POST in-flight; el siguiente tick dispara otra petición independientemente del estado de la anterior |

El término "fire-and-forget" aplica en su sentido estricto: NR dispara el POST y
**no procesa la respuesta**. El único comportamiento síncrono es el timeout de 5 s.

### Fallback: servicio AI caído o no deployado

| Escenario | Comportamiento de NR |
|---|---|
| URL de AI no configurada | NR omite el POST silenciosamente. TB sigue recibiendo telemetría normal |
| URL configurada pero `connection refused` | NR loguea warning (`ECONNREFUSED`). TB sigue recibiendo telemetría normal. `200` al servicio OPC |
| URL configurada, servicio cuelga sin responder | NR corta tras 5 s. Loguea timeout. TB sigue recibiendo telemetría normal. `200` al servicio OPC |
| Servicio AI devuelve `5xx` | NR loguea warning con el código. Ningún impacto aguas arriba |

**Garantía de diseño:** los fallos del servicio AI son invisibles para el
servicio OPC y para la persistencia en TB.

### Recuperación de scans perdidos

Los scans en los que el POST a AI falla o da timeout se consideran perdidos
**para inferencia en tiempo real**. Node-RED no reintenta ni encola.

Sin embargo, **todos los scans se persisten en TB independientemente del estado
del servicio AI**: la ingestión a TB usa el canal MQTT, independiente del POST
HTTP a AI. Si el servicio AI necesita recuperar una ventana de scans perdidos
tras un outage, puede consultarlos en TB vía REST API:

```
GET http://<tb-host>:9090/api/plugins/telemetry/DEVICE/<deviceId>/values/timeseries
    ?keys=value
    &startTs=<ms>
    &endTs=<ms>
```

El `deviceId` se obtiene listando devices del profile `sensor_planta` vía
`/api/tenant/devices`. El endpoint de telemetría y la autenticación siguen la
doc oficial de ThingsBoard.

Si el servicio AI decide aceptar la pérdida y no hacer backfill, también es
una decisión válida — queda a criterio del equipo AI en función de sus
requisitos de continuidad.

---

## Parte 2 — Writeback (AI → TB)

### Qué ofrece la plataforma

- Un **device TB pre-provisionado** (`ai-inference-<cliente>`) con su profile
  asociado `inference_results` y su access token — listo para recibir
  telemetría por REST.
- Una **rule chain asociada al profile** que persiste la telemetría en
  `ts_kv` como cualquier otro device (source of truth).
- **Entrega del token** al servicio AI por canal out-of-band (ver §A6).
- Documentación del endpoint REST y del esquema de campos esperados.

### Qué necesita la plataforma del servicio AI

- Un POST HTTP de telemetría por cada resultado de inferencia al endpoint
  TB acordado.
- Cuerpo JSON con el **mismo `ts`** del scan al que corresponde la inferencia
  (clave natural de correlación con los datos raw).
- Manejo local del token (no rotarlo, no exponerlo en logs).

### Endpoint

```
POST http://<tb-host>:9090/api/v1/<AI_ACCESS_TOKEN>/telemetry
Content-Type: application/json
```

- `<tb-host>` — hostname/IP de ThingsBoard alcanzable desde la red del
  servicio AI. En despliegue típico, `thingsboard` (DNS interno Docker) o el
  host del cluster según entorno.
- `<AI_ACCESS_TOKEN>` — token del device `ai-inference-<cliente>` entregado
  durante el deploy (ver §A6).
- Puerto `9090` — HTTP API de TB.

> **Nota de seguridad:** la API de TB exige el token en el **path de la URL**,
> no como header. Es una limitación del endpoint HTTP de device de TB CE.
> Evitar logs/traces que capturen la URL completa en claro.

### Request body

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

#### Campos

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

- **Un resultado = un POST.** No batchear varios scans en un solo POST (TB
  acepta arrays en `telemetry` pero rompería la idempotencia por `ts` única).
- **`ts` debe coincidir exactamente con el del scan** que NR envió al servicio
  AI. No usar `Date.now()`: rompe la correlación con la telemetría raw y anula
  la idempotencia.
- **Cardinalidad libre en `values`**: el schema anterior es mínimo; se pueden
  añadir keys sin renegociar el contrato.
- **Alarmas por inferencia** (`alarm_level`, `alarm_message`): el servicio AI
  decide cuándo emitirlas comparando su `score` contra thresholds definidos por
  el cliente. Son **opcionales** — un writeback sin `alarm_level` se interpreta
  como nivel `0`. No son alarmas nativas de TB (la rule chain del profile
  `inference_results` puede opcionalmente convertirlas en TB alarms, ver
  [`../architecture/alarm-propagation.md`](../architecture/alarm-propagation.md)).

### Ejemplo ejecutable

Simula el POST que el servicio AI hará tras computar la inferencia para un scan:

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

### Respuestas

| Código | Cuerpo | Cuándo |
|---|---|---|
| `200 OK` | vacío | Telemetría aceptada y procesada por la rule chain |
| `401 Unauthorized` | vacío | Token inválido, revocado o expirado |
| `400 Bad Request` | JSON con `message` | Body malformado, `ts` fuera de rango, tipo de dato no soportado |
| `404 Not Found` | vacío | Token existe pero device fue borrado (estado inconsistente) |

> TB no devuelve confirmación de persistencia en la DB (la rule chain es async).
> Un `200` confirma aceptación en el pipeline interno de TB, no aterrizaje en el
> almacén de timeseries. Fallos posteriores se observan como ausencia de datos,
> no como error en la respuesta.

### Casos de error operacionales

| Situación | Comportamiento esperado del servicio AI |
|---|---|
| TB responde `401` | Token revocado/rotado. Log de error crítico, detener writebacks, alertar a la plataforma para recibir nuevo token |
| TB responde `404` | Device borrado. Log de error crítico, alertar a la plataforma. No intentar recrear — el servicio AI **no** tiene permisos para crear devices |
| TB responde `400` | Bug en el servicio AI (body malformado, tipo incorrecto). Log de error con el body enviado + respuesta de TB. Descartar el writeback, no reintentar |
| TB timeout / 5xx | Reintento con backoff exponencial (recomendado: 3 reintentos, base 1 s, max 30 s). Tras agotar reintentos, descartar. El scan se considera perdido para inferencia histórica (aunque la raw siguió llegando normalmente) |
| `ts` >> tiempo actual (error en cálculo) | TB lo acepta. Los dashboards lo mostrarán en el futuro. El servicio AI debe tener sanity check antes de enviar |

---

## Device + profile pre-provisionados por la plataforma

El onboarding (`python3 -m deploy.onboarding`) crea idempotentemente por cliente:

| Entidad | Nombre | Rol |
|---|---|---|
| Device profile | `inference_input` | Audit-trail del snapshot LOCF enviado al servicio AI; NR lo publica en paralelo al POST de inferencia |
| Device profile | `inference_results` | Define la rule chain y los CFs para todos los devices de inferencia de la plataforma |
| Device | `ai-inference-<cliente>` | Receptor de writebacks del servicio AI para la planta |
| Access token | (generado por TB) | Credencial que el servicio AI usa en el path de la URL (Parte 2) |

El servicio AI **no crea entidades en TB**. Solo POSTea telemetría usando el
token que la plataforma le entrega en el onboarding del entorno.

---

## Anexos — asunciones y decisiones

Estas asunciones son parte del contrato. Si alguna no se cumple, conviene
renegociar antes de integrar.

### A1 — `ts` como clave de correlación (sin dedup server-side)

El `ts` del writeback es el `sourceTimestamp` que NR envió al servicio AI en el
POST de `/api/inference`. Esto permite:

- **Correlación natural** con la telemetría raw en TB: el score del scan del
  instante T se puede unir con los valores de los N sensores del mismo T, por
  coincidencia de `ts`.
- **Idempotencia**: si el servicio AI reintenta un writeback (p.ej. tras un
  timeout transitorio), el mismo `ts` sobrescribe el valor anterior sin duplicar.

No usar `Date.now()` ni ningún otro reloj del servicio AI — rompe la
correlación con la telemetría raw y anula la idempotencia.

### A2 — Cadencia periódica y timeouts

Cadencia **constante** al servicio AI: un POST cada `inference_emit_interval_ms`
(default `40000` ms). El servicio AI recibe tráfico regular independientemente
del patrón bimodal del OPC Client aguas arriba (full scans + CoV events), que
NR desacopla mediante ingesta event-driven hacia TB y emit periódico hacia AI.

Si la inferencia tarda más de 5 s, la arquitectura correcta es **aceptar el
POST rápido (`202 Accepted` o similar) y procesar en background**. Mantener la
conexión abierta más de 5 s provoca timeout en NR y el frame se considera
perdido para inferencia en tiempo real (el frame siguiente llega ~40 s después
con un snapshot LOCF fresco).

Si el modelo soporta inferencia batch (varios frames en una sola operación), el
servicio AI debe desempaquetar el batch en N writebacks separados, uno por `ts`.
No se acepta un array de scores bajo un único `ts`.

### A3 — Qué se retorna en el body de inferencia

NR descarta el body de respuesta del POST a `/api/inference`. El body de
respuesta del servicio AI es libre (puede devolver `{}`, el score, un status
string, etc.) — no hay contrato de respuesta. Solo se impone el timeout de 5 s.

### A4 — Writeback es responsabilidad del AI

Node-RED no participa en el camino de resultados. El servicio AI escribe sus
outputs a ThingsBoard por el canal REST descrito en Parte 2. Ninguna llamada de
vuelta hacia NR forma parte del contrato. Si el servicio AI necesita datos
históricos, la fuente es TB vía REST API (ver §Recuperación de scans perdidos),
no NR.

El writeback es fire-and-forget: el servicio AI hace el POST y sigue. No hay
callback de TB; la persistencia se verifica por observabilidad (dashboards,
queries ad-hoc). Los reintentos en caso de fallo transitorio son decisión del
servicio AI; TB es idempotente frente a reintentos con mismo `ts`.

### A5 — Red y DNS

Si el servicio AI está en el mismo compose que TB, usa DNS interno
(`thingsboard:9090`). Si está externo, necesita ruta de red o proxy hacia el TB
de la planta. La plataforma no gestiona la conectividad de red del servicio AI.

Todos los servicios del monorepo (`base`, `ai-advanced`, `blockchain`) deben
estar en la red `truedata-net`. En esa red, TB es accesible por DNS interno
como `thingsboard:9090`.

### A6 — Entrega y rotación de tokens

El access token del device `ai-inference-<cliente>` se entrega al equipo AI
**vía fichero `.env` generado por el onboarding de la plataforma** y consumido
por Docker compose. El mecanismo completo (ruta, shape, arranque ordenado,
smoke test unilateral, troubleshooting) está formalizado en
[`secrets-delivery.md`](secrets-delivery.md).

Resumen de rotación: gobernada por `--force` en el onboarding
(`python3 -m deploy.onboarding --force`). Al recibir `401` en un writeback, el
servicio AI debe detener writebacks y alertar a la plataforma — probable
rotación no anunciada o token corrupto. Procedimiento completo en
[`secrets-delivery.md`](secrets-delivery.md).

### A7 — Warmup y fallo aislado del AI

Los caminos NR→TB (telemetría event-driven) y NR→AI (inferencia periódica) son
independientes. Si el servicio AI cae, la telemetría raw sigue llegando a TB sin
interrupción. Los frames correspondientes a los ticks mientras AI está caído
simplemente no aparecen en el device `ai-inference-<cliente>`.

**Warmup gate.** NR no emite a AI hasta que todos los N tags de `EXPECTED_TAGS`
hayan aparecido al menos una vez en algún scan entrante. Durante warmup el
function node hace `node.log` con cuántos tags faltan (nivel debug). No hay
timeout explícito — el warmup acaba cuando los N tags se han visto, ni antes
ni después.

Restart de NR: `lastSeen` vive en memoria y se pierde con el proceso. Tras un
restart, el warmup se repite hasta recibir un full scan del OPC Client (típico
≤34 s en FR_ARAGON si el OPC Client respeta §A9).

**Caso URL de AI sin configurar:** si `ai_inference_url` no está seteado en
`runtime_config.json`, `fn_emit_periodic` omite silenciosamente el POST.

### A8 — Reproducibilidad del snapshot (sin audit trail en TB)

En la implementación simplificada, NR no duplica el snapshot enviado al AI
como telemetría en TB (antes se publicaba en el device `inference-input`).
Si se requiere reproducibilidad exacta del input del modelo, el propio
servicio AI puede persistir el payload recibido, o el servicio blockchain
puede hashear el body del POST que reciba (ver
[`blockchain-writeback.md`](blockchain-writeback.md) §A3).

El device profile `inference_input` sigue provisionado en TB por el
onboarding para compatibilidad, pero queda sin consumo desde NR hasta que
algún cliente lo reintroduzca.

### A9 — Full-scan garantizado tras reconexión (asunción OPC Client)

El pipeline asume que **el OPC Client emite un scan completo con todos los tags
como primera publicación tras una reconexión o al arranque**. Esta asunción
permite al pipeline recuperarse del warmup sin blackouts prolongados: todos los
tags se refrescan en un solo evento y los ticks siguientes emiten frame válido.

**Evidencia empírica:** de los 8 outages detectados en el dump FR_ARAGON
(duración 0.1 h a 508 h), 7 se recuperan con cardinalidad 27 en el primer scan,
y el octavo en el segundo scan (ambos con timestamp idéntico al milisegundo).
Comportamiento consistente con OPC-UA `CreateSubscription` → `PublishRequest`
que entrega snapshot inicial de todos los monitored items.

**Degradación si la asunción falla:** sin full-scan post-reconexión, el LOCF
retiene los últimos valores conocidos indefinidamente. Los frames al AI salen
puntualmente pero con valores obsoletos para los tags que no volvieron a
cambiar. La detección de esta condición es responsabilidad del modelo (o de un
cross-check externo con TB raw).

### A10 — Alarmas por inferencia (alarm_level / alarm_message)

El servicio AI es quien **decide cuándo el score indica una situación de alarma**
y lo señaliza en su writeback a TB mediante los campos `alarm_level` (0-3) y
`alarm_message`. El pipeline NR → AI **no transporta** información de alarmas:
el AI las evalúa contra thresholds empíricos del cliente (definidos fuera de
este contrato) y las emite junto al resto del writeback.

- Schema y semántica de los campos: ver §Parte 2 → Campos.
- Arquitectura global de alarmas en el sistema (inferencia AI + sensor raw):
  ver [`../architecture/alarm-propagation.md`](../architecture/alarm-propagation.md).

NR ignora estos campos — su responsabilidad termina al postear el snapshot al AI.

---

## Evolución posible (no implementado)

La implementación actual es **LOCF puro + emit periódico** (T = 40 s en
defaults FR_ARAGON). Trade-offs conscientes y evoluciones consideradas:

- **TTL per-frame (stale detection duro).** Descartar el frame si algún tag
  supera un umbral de staleness. Evaluado en una iteración previa y retirado
  por simplicidad — añadía complejidad operacional (tuning per-cliente) sin
  evidencia de beneficio real en FR_ARAGON (full-scan post-reconexión hace
  la staleness infrecuente en operación normal). Se puede reintroducir si
  una planta futura lo justifica.
- **Freshness vector per-tag (`fresh: {tag: age_ms}`).** Emitir siempre junto
  con un vector de edad por tag; el modelo decide cómo ponderar. Más expresivo
  que un skip binario pero requiere cambiar el contrato `/api/inference` y
  potencialmente reentrenar. Pendiente si el equipo AI lo solicita.
- **TTL per-tag** (en lugar de global). Útil si en clientes futuros aparecen
  sensores legítimamente lentos (p.ej. estado de válvula que cambia cada hora)
  junto a sensores rápidos (flujo/presión). Implementación trivial: cambiar
  `max_tag_staleness_ms` a un objeto `{tag: ms}` con fallback global. No se
  implementa en FR_ARAGON porque todos sus 27 tags tienen la misma cadencia
  empírica (p99=34.4 s).
- **Ring buffer `seq_in_len` en NR** (entregar `(N, num_sensors)` al modelo).
  Desplazaría la responsabilidad de la cola temporal del AI a NR. Descartado:
  rompe el push-model stateless de la IA y añade state pesado (persistente) a
  NR. El servicio AI es el owner natural de su cola temporal.
- **Aggregation opcional (mean/median sobre ventana ≥ ciclo PLC).** Mimetiza
  el ETL del diseño original FlowGuardInference. Irrelevante para FR_ARAGON
  (cadencia 34 s, ventanas sub-ciclo son degeneradas). Se revisitará si
  algún cliente futuro tiene OPC sub-segundo donde smoothing aporte.

---

## Contrato de conexión (cerrado)

**Endpoint AI estándar:** `http://ai-advanced:5000/api/inference` en la
red Docker `truedata-net`. Puerto **5000**, path `/api/inference`,
método `POST`. Este valor es el que `deploy/clients/<CLIENT>.yaml` →
`ai_inference.url` inyecta en NR vía `runtime_config.json`. Si un
entorno requiere puerto/path distinto, se cambia en el manifest YAML —
la plataforma no asume nada hardcoded más allá del default.

**Fan-out a blockchain (roadmap, no implementado):** si la anclaje
on-chain se activa para la planta, el patrón propuesto es que el
**servicio AI haga push a blockchain** tras computar el score
(fire-and-forget HTTP, patrón idéntico a NR→AI). Ver
[`blockchain-writeback.md §Trigger`](blockchain-writeback.md#trigger--ai-hace-push-al-servicio-blockchain)
— marcado como recomendación futura, no implementado por `base/` en
el pipeline actual. Cuando se implemente, el servicio AI leerá la URL
desde su env var `BLOCKCHAIN_ANCHOR_URL` (típico:
`http://blockchain:6000/api/anchor`), no es secreto y no la entrega
`base/`. Si la env var está unset, el AI omite el push silenciosamente
(blockchain opcional).

---

## Preguntas abiertas

Puntos a alinear con el equipo AI antes de pasar a entorno compartido.

1. **Campos adicionales en el body de inferencia.** ¿El modelo requiere algún
   campo además de `ts` y `sensors` (p.ej. `client_id`, `model_version`,
   `plant_id`)? Si es necesario, Node-RED puede añadirlos sin cambio estructural.

2. **Estrategia de scans perdidos.** ¿El servicio AI implementará backfill contra
   la REST API de TB para recuperar ventanas perdidas tras un outage, o se acepta
   la pérdida y se compensa a nivel de modelo/monitorización?

3. **Tolerancia a valores stale por LOCF.** El frame es LOCF puro — un sensor
   que deja de publicar retiene su último valor indefinidamente. El servicio AI
   detecta esta condición correlacionando `sensors[tag]` con el `ts` del último
   punto de ese sensor en TB raw si necesita emitir `status: "degraded"`. NR
   no aporta señal de staleness per-tag (decisión de diseño — ver §Evolución
   para la alternativa descartada con TTL/freshness vector).

4. **Campos adicionales en el writeback.** ¿El servicio AI querría persistir
   explainability (SHAP values, feature importances), flags de drift, confidence
   intervals, o metadata del modelo? La plataforma acepta cualquier key adicional
   en `values` sin cambios en TB.

5. **Estrategia en bundles parciales** (ver §A4 writeback). ¿Inferir siempre
   (imputando) o solo en bundles completos? Decisión del equipo AI; documentar
   en su runbook.

6. **Cadencia máxima de writebacks.** TB CE tiene los rate limits desactivados
   por default. Si el servicio AI quiere hacer writebacks más frecuentes que 1
   por scan (p.ej. re-inferencia tras nuevo modelo), ¿qué cadencia máxima
   prevé? La plataforma configurará rate limits acorde.

7. **Observabilidad.** ¿El servicio AI expone métricas Prometheus (latencia,
   throughput, error rate)? Si sí, la plataforma puede scrapearlas desde el
   mismo stack de monitoring que TB/NR.

8. **Entornos.** ¿Dev/pre/prod tienen tokens distintos? Sí por defecto, pero
   confirmar que el servicio AI soporta multi-token en su config.

---

## Historial

| Fecha | Autor | Cambio |
|---|---|---|
| 2026-04-16 | David Palazon / Claude | Primera versión de `ai-inference.md` |
| 2026-04-16 | David Palazon / Claude | Primera versión de `ai-writeback.md` — cierra pregunta abierta 3 de inferencia. Device + profile pre-provisionados; transport REST con token per-device |
| 2026-04-17 | David Palazon / Claude | Rediseño para LOCF: `sensors` cardinalidad fija N vía carry-forward; asunciones A6/A7/A8 (LOCF mecánica, warm-up post-arranque, inference-input como audit trail); pregunta abierta sobre staleness; §Evolución posible documenta trade-offs descartados |
| 2026-04-19 | David Palazon / Claude | Fusión de `ai-inference.md` + `ai-writeback.md` en `ai-service.md` — un único doc cubre el ciclo completo del servicio AI |
| 2026-04-20 | David Palazon / Claude | Rediseño de cadencia AI: de **event-driven** a **periódica** (emit cada `inference_emit_interval_ms`=60 s default). Añadido TTL duro per-frame (§A9, `max_tag_staleness_ms`=120 s default). Warmup timeout explícito (§A7). Asunción formal de full-scan post-reconexión (§A10). `lastSeen` persistido en context-store file para evitar warmup en restart. Observabilidad vía `GET /api/debug/stats`. Justificación con mediciones sobre dump FR_ARAGON (722h). Pregunta abierta 3 (staleness) resuelta. |
| 2026-04-20 | David Palazon / Claude | Simplificación: T=60 → **40 s**. Retirados TTL per-frame, warmup timeout, endpoint `/api/debug/stats`, persistencia de `lastSeen` en filesystem store, audit trail a `inference-input`. El frame pasa a ser un **contrato de interfaz LOCF sin garantía de freshness** — la detección de sensor muerto queda delegada al modelo. `ts` del frame es `Date.now()` del tick, no `sourceTimestamp` del PLC. Sección Evolución lista las capacidades retiradas como reintroducibles si un cliente futuro lo justifica. |
