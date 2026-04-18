# Contrato ML Inference — `POST /api/inference`

Contrato HTTP entre **Node-RED** y el **servicio ML** de inferencia.
Este documento es la referencia de implementación para el equipo que
desarrolla y opera el servicio ML.

---

## Resumen del contrato

### Qué ofrece Node-RED

- Un `POST` HTTP por cada scan del PLC al endpoint del servicio ML,
  emitido en paralelo a la persistencia en ThingsBoard.
- Un body JSON compacto con el timestamp del scan y todas las lecturas
  (`{ts, sensors}`), sin pre-procesado ni filtrado.
- Despacho independiente: la disponibilidad y latencia del servicio ML
  no afectan a la persistencia en ThingsBoard ni al acuse al servicio
  OPC.
- El scan completo queda persistido en ThingsBoard vía el otro camino
  del pipeline, disponible por REST API como fuente de verdad para
  backfill.

### Qué necesita Node-RED del servicio ML

- Un endpoint HTTP accesible que acepte POST con `Content-Type:
  application/json`.
- Respuesta (cualquiera, 2xx/4xx/5xx) en menos de 5 s en condiciones
  normales. Node-RED corta cualquier petición que exceda ese timeout.
- Que el servicio ML sea autónomo en el writeback de resultados a TB
  (Node-RED no participa en ese camino).
- Colaboración en las preguntas abiertas al final del documento.

---

## Endpoint (que debe exponer el servicio ML)

```
POST http://<ml-host>:<ml-port>/<ml-path>
Content-Type: application/json
```

La URL completa se configura en Node-RED en tiempo de despliegue.
El path exacto (`/api/inference`, u otro) se acuerda entre equipos; lo
relevante es que coincida con lo configurado en Node-RED.

---

## Request body (lo que el servicio ML recibirá)

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

### Campos

| Campo | Tipo | Descripción |
|---|---|---|
| `ts` | number (Unix ms) | `sourceTimestamp` del bundle OPC-UA que disparó esta inferencia. Idéntico al `ts` persistido en TB — sirve como clave natural para correlacionar inferencia con telemetría raw e inference-input snapshot |
| `sensors` | object | Diccionario `{tag_name: value}` con **cardinalidad fija N** = `EXPECTED_TAGS` configurados en NR (27 para FR_ARAGON; futuros clientes pueden tener otro N). Construido por Node-RED vía **carry-forward** sobre el estado `lastSeen` |
| `sensors.<tag>` | number \| boolean \| string | Valor del sensor. Puede ser el valor "fresco" del bundle actual, o un valor carry-forward del último bundle en el que ese tag apareció |

### Reglas semánticas

- **Cadencia event-driven, no wall-clock**. Cada bundle OPC-UA entrante (post warm-up) dispara un POST al servicio ML. Cadencia típica **≥34 s** cuando el pipeline recibe full scans; puede ser sub-segundo cuando llegan **CoV events** (Change-of-Value — notificaciones OPC-UA aisladas para tags de alta frecuencia como el watchdog `Heart_Bit` o analógicos configurados sin deadband, es decir, sin umbral mínimo de cambio antes de notificar). El servicio ML debe tolerar ritmos irregulares.
- **Cardinalidad fija `|sensors| = N`**. `N = |EXPECTED_TAGS|` por cliente. Nunca varía. Si el bundle entrante tiene menos tags, los que falten se rellenan con su valor más reciente conocido (LOCF). Si el bundle trae tags adicionales (nuevos sensores en campo), NR los persiste en TB raw pero **no los añade al payload ML** — requieren rebootstrap del modelo con nuevo `EXPECTED_TAGS`.
- **Los nombres de tags son literales del PLC** (no normalizados).
- **Warm-up gate**. Tras un restart de NR, el primer POST a ML se emite **solo cuando todos los N tags de `EXPECTED_TAGS` han aparecido al menos una vez en algún bundle**. Antes, NR no postea a ML (el raw path sí funciona). Ver §A7.

### Garantías sobre el campo `sensors`

- **Nunca contiene `null` ni `undefined`**. NR filtra valores nulos al actualizar su state LOCF; el snapshot siempre trae valores reales del último bundle válido por tag.
- **Contiene exactamente los tags de `EXPECTED_TAGS`**. Tags fuera del set no entran al snapshot (sí persisten en TB raw por separado).
- **El `ts` del snapshot corresponde al `ts` del bundle que disparó la inferencia**, no al instante de envío. Los valores de tags que no llegaron en ese bundle vienen por carry-forward (LOCF) del último bundle válido por tag.

### Detección de sensor dropout (stale LOCF)

NR no implementa timers de stale ni alarmas de sensor caído. Si un sensor dejara de emitir (avería persistente), el snapshot seguirá recibiendo su último valor conocido indefinidamente vía LOCF — limitación consciente del diseño: NR aporta cardinalidad fija sin estado temporal de frescura.

**Responsabilidad del servicio ML:** comparar el `ts` del snapshot entrante contra el `ts` del último punto de cada sensor individual en TB raw (`GET /api/plugins/telemetry/DEVICE/{sensor}/values/timeseries`). Si el gap es mayor que N ventanas operativas, emitir `status: "degraded"` en el writeback (ver `ml-writeback.md`).

### Estabilidad del tipo de valor

NR no valida el tipo del valor de cada tag. El mismo `sensors[tag]` puede ser `float` en una inferencia y `string` en la siguiente si el PLC cambia el tipo de la variable subyacente. El ML debe hacer sanity-check de tipos en su preproc (p.ej. `isinstance(v, (int, float))`) y rutar a un fallback si el tipo no es el esperado.

---

## Ejemplo ejecutable

Simulando la llegada de un scan al servicio ML:

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

---

## Comportamiento de Node-RED hacia el servicio ML

Node-RED actúa como **disparador**, no como consumidor del resultado:

| Aspecto | Comportamiento |
|---|---|
| Procesamiento de la respuesta | NR **descarta** el body y el código. Cualquier 2xx/4xx/5xx se loguea para observabilidad y se ignora funcionalmente |
| Timeout | **5000 ms**. Si el servicio ML no responde en 5 s, NR cancela la conexión. El siguiente scan llega ~34 s después |
| Reintentos | Ninguno. Un POST fallido (timeout, error de red, 5xx) no se reenvía |
| Concurrencia | Un POST por scan; NR no encola ni buffera si el servicio ML se cuelga |

El término "fire-and-forget" aplica en su sentido estricto: NR dispara
el POST y **no procesa la respuesta**. El único comportamiento síncrono
es el timeout de 5 s.

---

## Asunciones explícitas

Estas asunciones son parte del contrato. Si alguna no se cumple,
conviene renegociar antes de integrar.

### A1 — El servicio ML expone un endpoint HTTP con POST JSON

Endpoint accesible desde la red donde corre Node-RED, que acepta
`Content-Type: application/json` y tolera el body especificado
en §Request body.

### A2 — Respuesta en < 5 s en condiciones normales

Si la inferencia es más larga que eso, la arquitectura correcta es
**aceptar el POST rápido (`202 Accepted` o similar) y procesar en
background**. Mantener la conexión abierta más de 5 s provoca timeout
en Node-RED y el scan se considera perdido para inferencia.

### A3 — Writeback a TB es responsabilidad del servicio ML

Node-RED no participa en el camino de resultados. El servicio ML
escribe sus outputs a ThingsBoard por el canal que decida (REST API
de TB, MQTT, etc.) y, si corresponde, a otros consumidores downstream
(blockchain, etc.).

Las entidades en ThingsBoard que el servicio ML necesite para escribir
sus resultados (un device "inference results", un profile con rule
chain específica, calculated fields, etc.) se pueden pre-provisionar
desde el deploy pipeline — ver la pregunta abierta 3 al final.

### A4 — El servicio ML no depende de NR más allá de recibir el scan

Ninguna llamada de vuelta hacia NR forma parte del contrato. Si el
servicio ML necesita datos históricos, la fuente es TB (ver §Recuperación
de scans perdidos), no NR.

### A5 — Un fallo del servicio ML no bloquea la persistencia en TB

NR dispara el POST a ML y el publish a TB en paralelo. Si el servicio
ML está caído, TB sigue recibiendo telemetría normalmente y el servicio
OPC recibe su `200` sin retraso. El único impacto de un fallo ML es la
pérdida de inferencia en tiempo real para los scans afectados.

**Caso adicional — URL de ML sin configurar:** si el operador no ha
seteado `ML_INFERENCE_URL` en NR (o el manifest de onboarding lo dejó
a `null`), NR omite silenciosamente la salida 2. TB sigue recibiendo
telemetría raw; el servicio ML no recibe nada. El ACK al servicio OPC
incluye `"inference": "disabled"` para que sea observable.

### A6 — LOCF (Last Observation Carry Forward) — cómo se construye `sensors`

NR mantiene un estado en memoria `lastSeen = {tag → value}` que actualiza
con cada bundle entrante. Al construir el payload ML:

1. Para cada `tag` en `EXPECTED_TAGS`, busca su valor en `lastSeen`.
2. Usa el valor del **bundle actual** si el tag viene en él;
   caso contrario usa el valor previo (carry-forward).
3. Emite el POST con **los N tags completos** y `ts` = `ts del bundle actual`.

Consecuencias para el servicio ML:
- Siempre recibe `N` sensores. No necesita imputar ni tolerar cardinalidad
  variable en el input.
- Un valor recibido puede ser **stale** (carry-forward de un bundle
  anterior). Si el sensor se congela o falla, el valor stale se
  mantendrá indefinidamente — NR no tiene timers de frescura por tag.
  La detección de staleness es responsabilidad del servicio ML (ver
  más abajo).

**Detección opcional de staleness** (responsabilidad del servicio ML, no
del pipeline): comparar el `ts` del snapshot recibido con el `ts` del
último punto del sensor individual en TB raw
(`GET /api/plugins/telemetry/DEVICE/<tag>/values/timeseries?limit=1`).
Si el gap supera N ventanas esperadas, emitir writeback con
`status: "degraded"` (ver [ml-writeback.md](ml-writeback.md) §A4).

### A7 — Warm-up post-arranque

Tras un restart de NR el estado `lastSeen` está vacío. NR **no postea
a ML** hasta que todos los N tags de `EXPECTED_TAGS` hayan aparecido
al menos una vez en algún bundle. Mientras tanto:

- Los bundles parciales que llegan (p.ej. solo `Heart_Bit`) **se
  persisten normalmente** en TB raw (per-sensor).
- El HTTP response de NR incluye `"inference": "warmup(X/N)"` con
  `X` = tags aún no vistos.
- No hay timeout de warm-up. Si un tag de `EXPECTED_TAGS` nunca aparece
  (ej. sensor siempre caído), el warm-up **nunca completa** y ML no
  recibe nada. En este caso, documentación operacional debe revisar
  la validez de `EXPECTED_TAGS`.

Duración típica del warm-up tras restart: 1 bundle full scan (~34 s).

### A8 — Inference-input device en TB como audit trail

Cada POST emitido a ML se publica también **en paralelo** a TB como
telemetría del device `inference-input` (profile `inference_input`).
El servicio ML no necesita hacer nada con este device, pero:

- **Reproducibilidad:** el snapshot exacto que el modelo vio queda
  almacenado en TB indexado por `ts`.
- **Auditoría + blockchain:** el servicio airtrace puede hashear este
  device para generar `payload_digest` reproducible
  (ver [airtrace-writeback.md](airtrace-writeback.md) §A3).
- **Debug:** si el score es anómalo, mirar `inference-input` muestra
  el input exacto del modelo en vez de reconstruirlo desde N devices
  raw.

---

## Fallback: servicio ML caído o no deployado

| Escenario | Comportamiento de NR |
|---|---|
| URL de ML no configurada | NR omite el POST silenciosamente. TB sigue recibiendo telemetría normal |
| URL configurada pero `connection refused` | NR loguea warning (`ECONNREFUSED`). TB sigue recibiendo telemetría normal. `200` al servicio OPC |
| URL configurada, servicio cuelga sin responder | NR corta tras 5 s. Loguea timeout. TB sigue recibiendo telemetría normal. `200` al servicio OPC |
| Servicio ML devuelve `5xx` | NR loguea warning con el código. Ningún impacto aguas arriba |

**Garantía de diseño:** los fallos del servicio ML son invisibles para
el servicio OPC y para la persistencia en TB.

---

## Recuperación de scans perdidos

Los scans en los que el POST a ML falla o da timeout se consideran
perdidos **para inferencia en tiempo real**. Node-RED no reintenta ni
encola.

Sin embargo, **todos los scans se persisten en TB independientemente
del estado del servicio ML**: la ingestión a TB usa el canal MQTT,
independiente del POST HTTP a ML. Si el servicio ML necesita recuperar
una ventana de scans perdidos tras un outage, puede consultarlos en TB
vía REST API:

```
GET http://<tb-host>:9090/api/plugins/telemetry/DEVICE/<deviceId>/values/timeseries
    ?keys=value
    &startTs=<ms>
    &endTs=<ms>
```

El `deviceId` se obtiene listando devices del profile `sensor_planta`
vía `/api/tenant/devices`. El endpoint de telemetría y la
autenticación siguen la doc oficial de ThingsBoard.

Si el servicio ML decide aceptar la pérdida y no hacer backfill,
también es una decisión válida — queda a criterio del equipo ML en
función de sus requisitos de continuidad.

---

## Preguntas abiertas para el servicio ML

Puntos a alinear antes de pasar a entorno compartido.

1. **URL del endpoint.** ¿Cuál será el hostname, puerto y path del
   endpoint de inferencia? ¿Se prevé un cambio por entorno
   (dev/pre/prod)?

2. **Campos adicionales en el body.** ¿El modelo requiere algún campo
   además de `ts` y `sensors` (p.ej. `client_id`, `model_version`,
   `plant_id`)? Si es necesario, Node-RED puede añadirlos sin cambio
   estructural.

3. ~~**Writeback a TB: formato y topología.** ¿Cómo escribirá el servicio
   ML sus resultados en TB — REST API, MQTT, qué device(s)?~~ **CERRADA
   (2026-04-16)**: contrato definido en
   [`ml-writeback.md`](ml-writeback.md). Transport REST con token
   per-device (`ml-inference-<cliente>`), profile `inference_results`.
   UCAM pre-provisiona el device y entrega el token out-of-band.

4. **Estrategia de scans perdidos.** ¿El servicio ML implementará
   backfill contra la REST API de TB para recuperar ventanas perdidas
   tras un outage, o se acepta la pérdida y se compensa a nivel de
   modelo/monitorización?

5. **Tolerancia a valores stale por LOCF.** ¿El modelo detecta cuando
   un valor ha dejado de cambiar durante N bundles (sensor congelado
   o averiado)? Recomendación: implementar la detección de staleness
   descrita en §A6 para marcar inferencias afectadas con `status:
   "degraded"` en el writeback.

---

## Evolución posible (no implementado)

La implementación actual es **LOCF ligero, event-driven**. El trade-off
principal es que un sensor averiado propaga su último valor
indefinidamente — ver la nota en §Detección de sensor dropout (stale
LOCF) sobre la responsabilidad compartida con el servicio ML.

Evoluciones consideradas y descartadas para el scope actual:

- **Snapshot builder con ventanas temporales fijas** (cadencia wall-clock,
  stale counters, null-out tras K ventanas sin update). Aporta robustez
  frente a dropouts pero introduce estado persistido y complejidad
  operativa en NR. Se revisitará si el LIMIT-1 causa impacto operativo
  real en producción.
- **Staleness detection en NR** (flag `stale: true` por tag en el
  payload). Más simple que el snapshot builder pero requiere schema
  adicional en el contrato. Pendiente si ML team lo solicita.
- **Rate limiting a 1 inferencia por ciclo PLC** (ignorar CoV events).
  Limpia la cadencia pero pierde detalle temporal. Alternativa:
  implementar en ML con dedup por ventana.


---

## Historial

| Fecha | Autor | Cambio |
|---|---|---|
| 2026-04-16 | David Palazon / Claude | Primera versión |
| 2026-04-16 | David Palazon / Claude | §Preguntas abiertas 3 cerrada con cross-ref a ml-writeback.md |
| 2026-04-17 | David Palazon / Claude | Rediseño para LOCF: `sensors` cardinalidad fija N vía carry-forward, asunciones A6/A7/A8 añadidas (LOCF mecánica, warm-up post-arranque, inference-input como audit trail), pregunta abierta 5 sobre staleness, §Evolución posible documenta trade-offs descartados |
