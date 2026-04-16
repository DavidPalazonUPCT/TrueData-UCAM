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
| `ts` | number (Unix ms) | Timestamp del PLC del scan. Idéntico al `ts` persistido en TB — sirve como clave natural para correlacionar inferencia con telemetría |
| `sensors` | object | Diccionario `{tag_name: value}` con **todas** las lecturas del scan, sin filtrado |
| `sensors.<tag>` | number \| boolean \| string | Valor del sensor tal cual lo envía el PLC |

### Reglas semánticas

- **Un scan = un POST**. Cadencia típica: ~34 s (variable por planta).
- **Los nombres de tags son literales del PLC** (no normalizados).
- **`sensors` contiene el scan completo, sin filtrar**. Si el modelo
  solo consume un subconjunto, el filtrado ocurre en el lado del
  servicio ML. Así, añadir o quitar sensores del PLC no requiere
  coordinar cambios en Node-RED.

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

3. **Writeback a TB: formato y topología.** ¿Cómo escribirá el servicio
   ML sus resultados en TB — REST API, MQTT, qué device(s)? Las
   entidades necesarias (device "inference results", profile específico,
   rule chain) se pueden pre-provisionar desde el deploy pipeline si se
   acuerda el diseño con antelación.

4. **Estrategia de scans perdidos.** ¿El servicio ML implementará
   backfill contra la REST API de TB para recuperar ventanas perdidas
   tras un outage, o se acepta la pérdida y se compensa a nivel de
   modelo/monitorización?
