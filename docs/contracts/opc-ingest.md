# Contrato OPC Ingest — `POST /api/opc-ingest`

Contrato HTTP entre el **servicio OPC** y **Node-RED**, con
**ThingsBoard** como sistema de persistencia downstream. Este documento
es la referencia de implementación para el equipo que desarrolla y
opera el servicio OPC.

---

## Resumen del contrato

### Qué ofrece Node-RED

- Un endpoint HTTP (`POST /api/opc-ingest`) que acepta el scan bulk de
  cada ciclo del PLC.
- Validación síncrona del payload con código de respuesta inmediato
  (`200` / `400`).
- Publicación de la telemetría a ThingsBoard por un camino independiente
  (Gateway MQTT API, transparente al servicio OPC).
- Auto-provisioning de devices per-tag en ThingsBoard: un tag nuevo no
  requiere intervención manual.

### Qué necesita Node-RED del servicio OPC

- Un `POST` HTTP por cada scan del PLC al endpoint acordado.
- Cuerpo JSON con **timestamp client-side del PLC** (`ts`, Unix ms) y
  **todas las lecturas del scan** (`values`) en un único mensaje.
- Store-and-forward local en el servicio OPC para cubrir indisponibilidad
  transitoria de Node-RED, preservando el `ts` original.
- Colaboración en las preguntas abiertas al final del documento.

---

## Endpoint

```
POST http://<host>:1880/api/opc-ingest
Content-Type: application/json
```

Donde `<host>` es el hostname/IP del contenedor Node-RED. En desarrollo
local, `localhost`. En despliegue real, el host acordado por entorno.

---

## Request body

```json
{
  "ts": 1776326159190,
  "values": {
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

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `ts` | number (Unix ms) | **Sí** | Timestamp del PLC del momento del scan. Único para todo el scan |
| `values` | object | **Sí, no vacío** | Diccionario `{tag_name: value}` con las lecturas del scan |
| `values.<tag>` | number \| boolean \| string \| object | Sí | Valor del tag. TB acepta estos tipos nativamente |

### Reglas semánticas

- **Un scan = un POST = un `ts`**. Todos los tags del mismo scan
  comparten timestamp. No enviar tags del mismo scan en POSTs separados.
- **`tag_name` es el nombre literal del tag en el PLC**, sin prefijo ni
  normalización. Identifica al device en TB 1:1.
- **Cardinalidad libre**: el payload puede contener N tags (no se valida
  el número).
- **`value: null` o `undefined` ≡ tag ausente del bundle**. Un bundle `{ts, values: {X: null}}` devuelve `200 OK` pero X no entra al estado interno de Node-RED (el estado **LOCF** — Last Observation Carry Forward — que rellena los valores que faltan en futuros bundles con la última lectura válida por tag). Consistente con OPC-UA: un DataValue con StatusCode Bad suele llevar `value: null`.
- **Cambio de tipo del valor entre bundles no validado**. El mismo `tag` puede enviar `float` en un bundle y `string` en otro; NR propaga ambos. Responsabilidad del consumidor ML hacer sanity-check de tipos.

---

## Ejemplo ejecutable

Copy-paste, funciona contra una instancia recién arrancada:

```sh
curl -s -X POST http://localhost:1880/api/opc-ingest \
  -H "Content-Type: application/json" \
  -d "{
    \"ts\": $(date +%s%3N),
    \"values\": {
      \"POT_CCM\": 300.0,
      \"TURB1\": 0.0,
      \"FT1\": 1322.22
    }
  }"
```

Respuesta esperada:

```json
{"status":"ok","tags":3}
```

---

## Respuestas

| Código | Cuerpo | Cuándo |
|---|---|---|
| `200 OK` | `{"status": "ok", "tags": <N>}` | Payload válido, parseado y publicado al broker MQTT de TB. `<N>` = número de tags recibidos |
| `400 Bad Request` | `{"status": "error", "reason": "body not valid JSON object"}` | Body ausente, no parseable como JSON, o de tipo distinto a objeto (array, primitivo) |
| `400 Bad Request` | `{"status": "error", "reason": "ts missing or not finite number"}` | `ts` ausente, no es `typeof number`, o es `NaN`/`Infinity` |
| `400 Bad Request` | `{"status": "error", "reason": "ts outside acceptable window (now-30d .. now+5min)"}` | `ts` fuera de la ventana aceptable (ver A6) |
| `400 Bad Request` | `{"status": "error", "reason": "values must be non-empty object"}` | `values` ausente, no es objeto, es un array, o está vacío |

> El `200` confirma parsing + dispatch al broker. **No** es ACK de
> persistencia en la DB de TB. Un fallo posterior en el broker se
> observa como ausencia de telemetría en TB, no como error en esta
> respuesta.

### Validaciones que rechazan el POST

| Orden | Check | Fallo → reason |
|---|---|---|
| 1 | body JSON, typeof "object", no null, no array | `"body not valid JSON object"` |
| 2 | `typeof ts === "number"` && `Number.isFinite(ts)` | `"ts missing or not finite number"` |
| 3 | `ts ∈ [now-30d, now+5min]` | `"ts outside acceptable window (now-30d .. now+5min)"` |
| 4 | `typeof values === "object"`, no null, no array, ≥1 key | `"values must be non-empty object"` |

NR **no valida**: cardinalidad (el objeto `values` puede tener 1 o
centenares de tags), tipo de cada valor, existencia previa de los tags
como devices en TB, ni rango/plausibilidad de los valores.

> **JSON con keys duplicadas** (p.ej. `{"values": {"X": 1, "X": 2}}`)
> es undefined behaviour en el estándar. NR queda con la última
> (`X = 2`); el cliente OPC no debe producir payloads así.

---

## Asunciones explícitas

Estas asunciones son parte del contrato. Si alguna no se cumple,
conviene renegociar antes de integrar.

### A1 — `ts` es client-side del PLC

El `ts` debe ser el instante de la medición en la planta, generado por
el PLC o por el servicio OPC en el momento del scan. **No** debe ser
el instante de envío del POST.

Un timestamp asignado en el momento de envío pierde la temporalidad
real si el POST se retrasa (fallo de red, reintentos, store-and-forward).
Con `ts` del PLC, los datos recuperados tras cualquier retraso
conservan su posición temporal original.

### A2 — 1 POST = 1 scan completo

Cada ciclo del PLC se envía en un único POST con **todos los tags del
scan**. Esto garantiza que las lecturas atómicas de un ciclo comparten
el mismo `ts` y quedan correlacionables aguas abajo (en TB y en el
servicio ML).

### A3 — Idempotencia por `ts`

Reenviar un scan con el mismo `ts` (tras un fallo de red, un restart
del servicio OPC, o un store-and-forward) **no crea duplicados** en
TB.

TB usa `(device, key, ts)` como clave de timeseries: un segundo
envío con el mismo `ts` sobrescribe el valor anterior. Si el valor
coincide, el efecto es un no-op; si el valor cambió (p.ej. una
corrección), queda el último enviado.

Consecuencia práctica: el servicio OPC puede reenviar de forma
conservadora sin miedo a inflar la base de datos.

### A4 — Store-and-forward es responsabilidad del servicio OPC

Si Node-RED está caído o inalcanzable, el POST falla con error de red
(`connection refused`, `timeout`). La recuperación es responsabilidad
del servicio OPC:

- Encolar los scans localmente (preferentemente persistente en disco).
- Reenviarlos cuando Node-RED vuelva, con su `ts` original del PLC
  preservado.
- Métricas de backlog para detectar colas crecientes.

Igualmente, una pérdida de conexión entre el servicio OPC y el PLC es
opaca para Node-RED: se manifiesta como ausencia de POSTs. El monitoreo
de disponibilidad del PLC vive en el servicio OPC.

### A5 — Sin autenticación (decisión temporal)

El endpoint `/api/opc-ingest` **no exige autenticación** hoy. Es una
decisión deliberada para simplificar la integración inicial, no un
olvido.

Mitigaciones asumidas en el entorno actual:
- Red interna entre el servicio OPC y Node-RED (puerto 1880 no
  expuesto públicamente).
- Firewall de host restringiendo el acceso a IPs conocidas.

Cuando se acuerde un mecanismo (token compartido, mTLS, header
custom), se documentará como campo adicional del contrato sin romper
compat con integraciones existentes.

### A6 — `ts` en ventana [now-30d .. now+5min]

NR rechaza (`400`) cualquier POST con `ts` fuera de esta ventana respecto al reloj del host de NR. El rango tolera:

- Store-and-forward del servicio OPC hasta 30 días de backlog.
- Clock skew moderado entre el PLC/servicio OPC y el host de NR (±5 min en el futuro).

Valores fuera de rango (p.ej. `ts=0` por bug del cliente, `ts` de años atrás por replay de dumps antiguos) se rechazan para prevenir contaminación del histórico TB y queries confusas.

---

## Casos de error operacionales

| Situación | Comportamiento esperado |
|---|---|
| `ts` como string ISO (`"2026-04-16T08:35:59Z"`) | Rechazo con `400 ts missing or not finite number`. El contrato exige Unix ms como `number` |
| `values: []` (array) o `values: null` | Rechazo con `400 values must be non-empty object` |
| Tag nuevo nunca antes visto | Aceptado. NR auto-provisiona el device en TB vía Gateway MQTT `connect` |
| Servicio ML caído aguas abajo de NR | No afecta a este endpoint. El `200` no depende del servicio ML |
| Node-RED caído | POST falla con error de red. Servicio OPC debe aplicar store-and-forward (ver A4) |
| `ts` epoch (`0`) o negativo | Rechazo con `400 ts outside acceptable window`. Indica bug en el cliente, no se ingesta |
| `ts` futuro > now+5min | Rechazo con `400 ts outside acceptable window`. Indica clock skew extremo o ts erróneo |
| `ts` muy antiguo (> 30 días atrás) | Rechazo con `400 ts outside acceptable window`. Requiere replay con desplazamiento temporal si se desea reingestar |
| Content-Type no JSON (p.ej. `text/plain`) | Rechazo con `400 body not valid JSON object` |
| Body vacío | Rechazo con `400 body not valid JSON object` |

---

## Preguntas abiertas para el servicio OPC

Puntos a alinear antes de pasar a entorno compartido.

1. **Store-and-forward persistente.** ¿El cliente OPC implementa
   persistencia en disco de los scans no enviados? ¿Qué tamaño máximo
   de backlog soporta y qué política tiene cuando se llena?

2. **Adaptabilidad al contrato.** ¿El cliente OPC puede adaptar el
   formato del POST a este contrato (`{ts, values}`), o existen
   constraints sobre el body que obliguen a negociar cambios en la
   forma?

3. **Flexibilidad del path.** ¿La URL de destino (`/api/opc-ingest`)
   es configurable en el cliente OPC, o hay un path hardcoded que
   requeriría que Node-RED adopte esa convención?
