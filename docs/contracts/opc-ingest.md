# Contrato OPC Ingest — `POST /api/opc-ingest`

Contrato entre el cliente OPC y Node-RED (NR) del pipeline v2. Este
documento es la referencia de implementación para el equipo del
cliente OPC.

- **Dirección:** cliente OPC → NR
- **Modelo de despliegue:** una instancia NR por planta. El
  identificador del cliente es implícito por el entorno.
- **Autenticación:** **sin auth por ahora.** Asunción documentada, no
  decisión permanente. Ver §Seguridad.

---

## Endpoint

```
POST http://<host>:1880/api/opc-ingest
Content-Type: application/json
```

Donde `<host>` es el hostname/IP donde corre el contenedor de Node-RED.
En desarrollo local, `localhost`. En despliegue real, el host del
cluster Docker de la planta.

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
| `ts` | number (Unix ms) | **Sí** | Timestamp del PLC del momento del scan. Único para todo el scan. Debe ser client-side del PLC (no `Date.now()` del cliente OPC) |
| `values` | object | **Sí, no vacío** | Diccionario `{tag_name: value}` con las lecturas del scan |
| `values.<tag>` | number \| boolean \| string \| object | Sí | Valor del tag. NR no hace type-checking. ThingsBoard acepta estos tipos nativamente |

### Reglas semánticas

- **Un scan = un POST = un `ts`.** Todos los tags del mismo scan
  comparten el mismo timestamp. No enviar tags del mismo scan en POSTs
  separados.
- **`tag_name` es el nombre literal del tag en el PLC.** Sin prefijo de
  cliente, sin normalización. Se usa tal cual como identidad del device
  en TB.
- **`values` puede contener cualquier número de tags** (1, 27, 31, N).
  NR no valida cardinalidad.

---

## Ejemplo ejecutable

Copy-paste, funciona contra una instancia de NR recién arrancada:

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
| `200 OK` | `{"status": "ok", "tags": <N>}` | Payload válido. `<N>` = número de tags recibidos |
| `400 Bad Request` | `{"status": "error", "reason": "ts missing or not number"}` | `ts` ausente o no es `typeof "number"` |
| `400 Bad Request` | `{"status": "error", "reason": "values missing or empty"}` | `values` ausente, no es objeto, o está vacío |

> **Nota:** el `200` confirma que el payload se parseó y se publicó al
> broker MQTT. No es un ACK de persistencia en la DB de ThingsBoard.
> Un fallo posterior en el broker se vería como ausencia de telemetría
> en TB, no como error en esta respuesta. Ver
> [PLAN-001 §D.2.3](../architecture/PLAN-001) para el razonamiento.

---

## Validaciones que rechazan el POST

NR aplica validación mínima, orientada a detectar bugs del emisor sin
imponer un schema rígido:

| Check | Resultado si falla |
|---|---|
| `typeof payload.ts === "number"` | 400 `ts missing or not number` |
| `typeof payload.values === "object"` y no `null` y con ≥1 key | 400 `values missing or empty` |

**NO se valida:**

- El número de tags (varía por cliente).
- El tipo de cada `values.<tag>` (TB acepta string, boolean, double, long,
  JSON nativamente).
- Que los tag names existan como devices en TB (el Gateway MQTT API
  auto-provisiona).
- El rango o plausibilidad de los valores.

---

## Casos de error operacionales

### `ts` ausente o no numérico

**Causa típica:** enviar `ts` como string ISO (`"2026-04-16T08:35:59Z"`).
El contrato exige **Unix milliseconds como `number`**.

```sh
# MAL:
-d '{"ts": "2026-04-16T08:35:59Z", "values": {...}}'
# Bien:
-d '{"ts": 1776326159190, "values": {...}}'
```

**Por qué no se acepta silent default (`ts = Date.now()`):** rompería
store-and-forward sin que nadie se entere. Datos retrasados llegarían
marcados como "ahora" y se perdería la temporalidad real de la
medición. 400 duro es el comportamiento correcto.

### `values` vacío o no-objeto

**Causa típica:** enviar `values: []` (array) o `values: null`. El
contrato exige **objeto con al menos una key**.

### Pérdida de conexión con el PLC

**No es asunto de NR.** Si el cliente OPC pierde conexión al PLC, debe
resolverlo en su lado: store-and-forward local, reintentos con backoff,
métricas de backlog. NR solo observa la ausencia de POSTs.

### NR caído

Si NR está caído o inalcanzable, el POST falla con error de red
(`connection refused`, `timeout`). Responsabilidad del cliente OPC:
**encolar los scans localmente y re-enviarlos cuando NR vuelva.** Al
reenviar, se envían con su `ts` original del PLC (client-side timestamp,
preservado). TB almacenará los datos con su temporalidad real.

Ver [ADR-003 §2.3.1](../architecture/ADR-003.md) para el razonamiento
del client-side timestamp y su relación con store-and-forward.

---

## FAQ

**¿Puedo enviar 1 tag por POST en vez de bulk?**

Técnicamente sí, el endpoint lo acepta. Pero se pierde la semántica de
"atomicidad del scan" y se crean N `ts` distintos para lecturas que
físicamente ocurrieron juntas. El diseño asume **1 POST = 1 scan del PLC**.

**¿Puedo añadir un campo `client` o `plant_id`?**

No es necesario: una instancia de NR por planta hace el identificador
implícito por el entorno. Si se añade, NR lo ignorará silenciosamente.

**¿Qué hago si necesito enviar metadatos adicionales (calidad OPC,
estado de sensor)?**

Dos opciones:
1. Empaquetarlos como tags adicionales (`POT_CCM_quality`, etc.) dentro
   de `values`.
2. Solicitar una extensión del contrato; hoy solo `ts` + `values` están
   soportados.

**¿Cuántas peticiones por segundo soporta NR?**

El caso de uso es ~34 s por scan; es decir, ~0,03 req/s por instancia.
Muy por debajo de cualquier límite práctico de NR. Si la cadencia sube
significativamente (p.ej. ≤1 s), avisar a UCAM.

**¿Qué pasa si NR recibe un scan con un tag que antes no existía?**

NR envía un `v1/gateway/connect` idempotente al broker de TB, y TB
auto-crea el device con el profile correcto. Cero intervención manual.

---

## Seguridad

**Actualmente sin autenticación.** Asunción explícita: el endpoint
`/api/opc-ingest` confía en la red privada entre el cliente OPC y NR.

Esto es una asunción de dev, **no una decisión permanente**. Cuando
exista un canal de auth (token compartido, mTLS, header custom), se
documentará en este mismo contrato como campo adicional (header
`Authorization`, etc.) sin romper compat con integraciones existentes.

**Mitigaciones recomendadas hoy:**

- Red Docker interna aislada (el puerto 1880 no expuesto al público).
- Firewall de host restringiendo 1880 al cliente OPC.

---

## Referencias

- [ADR-003 §2.1](../architecture/ADR-003.md) — arquitectura pipeline v2
- [PLAN-001 §D.2](../architecture/PLAN-001) — contrato completo y razonamiento
- [PLAN-001 §D.5](../architecture/PLAN-001) — ejemplo end-to-end con datos reales
