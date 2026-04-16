# Contrato ML Inference — `POST /api/inference`

Contrato entre Node-RED (NR) y el servicio de inferencia ML del
pipeline v2. Este documento es la referencia para el equipo que
implementa el servicio ML.

- **Dirección:** NR → servicio ML
- **Modo:** fire-and-forget. NR no consume la respuesta.
- **Criticidad:** **no bloqueante.** Si el servicio ML está caído o
  lento, ThingsBoard sigue recibiendo telemetría normalmente.

---

## Endpoint (que debe exponer el servicio ML)

```
POST http://<ml-host>:<ml-port>/api/inference
Content-Type: application/json
```

La URL se configura en NR vía `flow.ML_INFERENCE_URL`. Si no está set,
NR no emite este POST (ver §Fallback). El path `/api/inference` es
convención UCAM pero puede coordinarse con el equipo ML si se prefiere
otro.

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
| `ts` | number (Unix ms) | Timestamp del PLC del scan. Idéntico al `ts` que se envía a TB — permite correlacionar con la telemetría persistida |
| `sensors` | object | Diccionario `{tag_name: value}` con **todas** las lecturas del scan. No filtrado |
| `sensors.<tag>` | number \| boolean \| string | Valor del sensor, tal cual viene del PLC |

### Semántica

- **NR envía todos los tags del scan, sin filtrar.** El servicio ML
  decide qué features consumir. Filtrar en NR acoplaría UCAM al modelo
  concreto.
- **Los nombres de tags son literales del PLC** (no normalizados).
- **Un scan = un POST.** Cadencia típica: ~34 s (variable según planta).
- **El `ts` es el mismo que el enviado a TB.** Atomicidad del scan.

---

## Ejemplo ejecutable (simulación desde curl)

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

## Qué se espera del servicio ML como respuesta

**NR ignora la respuesta.** Sea cual sea el status code, el body, o
incluso la ausencia de respuesta, NR no la procesa ni la reenvía.

Esto significa:

- No hace falta devolver un JSON específico a NR.
- No hace falta devolver `200`. Cualquier `2xx`, `4xx`, `5xx` es
  irrelevante para el flow de ingestión.
- La respuesta se registra en logs de NR (info si `2xx`, warning si
  otros) solo para observabilidad. No afecta el path de datos.

**Los resultados de inferencia NO se devuelven a NR.** El servicio ML
los envía por su propio camino:

- A **ThingsBoard**, usando su propio cliente HTTP/MQTT contra la API
  de TB.
- A **cualquier otro consumidor downstream** (ej. servicio de
  blockchain), también por su propio camino.

NR no es un broker de resultados. Actúa como disparador.

---

## Timeouts y SLA que impone NR

| Parámetro | Valor | Comportamiento |
|---|---|---|
| `requestTimeout` | **5000 ms** | Si el servicio ML no responde en 5 s, NR cancela la conexión y continúa. El error queda en logs como `"no response from server"` (`ETIMEDOUT`) |
| Reintentos | Ninguno | Un scan perdido por timeout o error no se reenvía. El siguiente scan llega ~34 s después |
| Concurrencia | Serial implícito | NR postea un scan por ciclo. No hay encolado ni buffering si el servicio ML se cuelga |

**Implicación para el servicio ML:** debe responder (o fallar rápido)
en < 5 s. Si la inferencia tarda más, la arquitectura correcta es
**aceptar el POST rápido y procesar en background**, devolviendo
inmediatamente un `202 Accepted` o similar.

---

## Fallback: servicio ML caído o no deployado

| Escenario | Comportamiento de NR |
|---|---|
| `flow.ML_INFERENCE_URL` no configurada | NR omite silenciosamente el POST a ML. TB sigue recibiendo telemetría normal |
| URL configurada pero `connection refused` | NR loguea warning (`ECONNREFUSED`). TB sigue recibiendo telemetría normal. Respuesta al cliente OPC: `200` |
| URL configurada, servicio cuelga sin responder | NR corta tras 5 s. Loguea timeout. TB sigue recibiendo telemetría normal. Respuesta al cliente OPC: `200` |
| Servicio ML devuelve `5xx` | NR loguea warning con el código. TB sigue recibiendo telemetría normal |

**Garantía de diseño:** un fallo del servicio ML **jamás** afecta a la
persistencia en ThingsBoard ni a la respuesta al cliente OPC. TB y
ML son paths independientes: NR los despacha en paralelo y ninguno
bloquea al otro.

---

## Configuración de la URL en NR

Dos caminos:

### Producción

Setear `flow.ML_INFERENCE_URL` como parte del flow persistido. UCAM se
encarga en el deploy pipeline.

### Desarrollo

El flow expone (solo cuando `NR_ADMIN_ENABLED=true` en el entorno)
tres endpoints auxiliares:

```sh
# Setear URL en runtime
curl -s -X POST http://localhost:1880/admin/set-ml-url \
  -H "Content-Type: application/json" \
  -d '{"url":"http://<ml-host>:<port>/api/inference"}'

# Leer URL actual
curl -s http://localhost:1880/admin/get-ml-url

# Limpiar URL (silencia la salida)
curl -s -X POST http://localhost:1880/admin/clear-ml-url
```

En producción, `NR_ADMIN_ENABLED` no se setea y estos endpoints
devuelven `404` byte-identical a un path inexistente.

---

## FAQ

**¿El servicio ML debe escuchar en `/api/inference` literalmente?**

Es convención UCAM; el path exacto se puede coordinar. Lo relevante es
que la URL configurada en `flow.ML_INFERENCE_URL` apunte al endpoint
que acepte el body especificado.

**¿El servicio ML puede exigir autenticación?**

Sí. NR postea con `Content-Type: application/json` y sin `Authorization`
por defecto. Si el servicio exige auth, hay que coordinar con UCAM
para añadir headers al POST (cambio trivial en el flow).

**¿Hay límite de tamaño del body?**

No impuesto explícitamente. El tamaño típico es ~3 KB para scans de
~30 sensores. NR no rechaza bodies grandes hasta los defaults de Node-RED
(varios MB).

**¿El servicio ML puede asumir que NR envía en orden cronológico?**

Sí, en el caso normal (scans en tiempo real). Si se reproducen datos
históricos vía store-and-forward del cliente OPC, los `ts` pueden
llegar fuera de orden de wall-clock pero siempre con su timestamp
real del PLC.

**¿Qué tags exactos voy a recibir?**

Depende de la planta. Cada instancia NR recibe los tags del cliente
OPC de esa planta. Ejemplo para una planta tipo: `POT_CCM`, `TURB1`,
`FT1`, `pH_Entrada`, `SH2_AguaBruta`, etc. El servicio ML debe ser
robusto a:
- Añadir o quitar tags sin redeploy del ML (el modelo usa los que
  reconoce).
- Cambios de nombres de tags se coordinan como cambio de contrato
  entre UCAM y el equipo ML.

**¿Cómo sé si NR me está enviando datos?**

Loguear cada POST recibido en el servicio ML. Si no llegan POSTs con
la cadencia esperada (~34 s), el problema está upstream de ML: cliente
OPC caído, NR sin ingestión, o `flow.ML_INFERENCE_URL` sin setear.

