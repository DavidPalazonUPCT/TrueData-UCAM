# Alarm propagation — arquitectura v2

Resumen de cómo se propagan las alarmas en el pipeline TrueData v2,
desde su origen hasta el frontend / dashboards operacionales.

El sistema soporta **dos tipos de alarmas** con orígenes distintos, que
coexisten sin interferir. Para el MVP regulatorio solo el **Tipo 1** está
implementado en contrato; el **Tipo 2** está diseñado y pendiente de
datos empíricos.

---

## Tipo 1 — Alarmas por inferencia AI

**Origen:** servicio de inferencia AI, tras evaluar su `score`.

**Quién las emite:** el servicio AI. El servicio conoce la semántica de
su `score` (anomaly score, probabilidad, clasificación numérica, etc.)
y tiene thresholds empíricos configurados por cliente. Al computar la
inferencia de un scan, decide el nivel de alarma y lo incluye en el
mismo POST de writeback a TB.

**Canal:** campo nuevo en el body del writeback AI (ver
[`../contracts/ai-service.md` §Parte 2 → Campos](../contracts/ai-service.md)):

| Campo | Valores |
|---|---|
| `values.alarm_level` | `0` normal · `1` warning · `2` critical · `3` emergency |
| `values.alarm_message` | string libre o `null` si `alarm_level == 0` |

Convención numérica alineada con severidades nativas de TB
(`WARNING`, `MINOR`, `MAJOR`, `CRITICAL`) para permitir mapeo directo
si en el futuro se activan TB alarm rules (ver §Propagación a TB alarms).

**Destino:** device `ai-inference-<CLIENT>` en TB, profile
`inference_results`. Los campos `alarm_level`/`alarm_message` quedan
almacenados como timeseries junto al resto del writeback
(`score`, `model_version`, `latency_ms`, `status`).

**Consumo por el frontend:** query estándar de timeseries del device:

```
GET /api/plugins/telemetry/DEVICE/<inference-device-id>/values/timeseries
    ?keys=score,alarm_level,alarm_message
    &startTs=<ms>&endTs=<ms>
```

Cada punto (`ts`, `alarm_level`) indica el nivel de alarma para el
scan de ese instante. Dashboards pueden:

- Mostrar serie temporal de `alarm_level` alineada con el `score`.
- Filtrar por `alarm_level >= 1` para obtener solo incidencias.
- Mostrar `alarm_message` como tooltip / detalle contextual.

---

## Tipo 2 — Alarmas por sensor raw (post-MVP)

**Origen:** TB alarm rules nativas declaradas en el profile
`sensor_planta`.

**Motivación:** alarmas operativas por sensor individual (p.ej.
`Q_SALIDA_D1 < 100 L/s durante 5 min` → `MAJOR`). No las evalúa el AI
— son thresholds deterministas sobre telemetría raw.

**Implementación propuesta:**

- Cada device del profile `sensor_planta` hereda alarm rules con
  `condition` + `clearCondition` + `severity`.
- TB emite las alarmas al sistema nativo (Alarms tab, notification
  center, REST API `/api/plugins/alarm/*`).
- Los thresholds se declaran en el profile y aplican automáticamente a
  todos los devices auto-provisionados (los 27 sensores de FR_ARAGON).

**Estado actual:** no implementado. Requiere:

1. Thresholds empíricos definidos por sensor (datos de FR_ARAGON).
2. Schema del bloque `profileData.alarms` en el profile
   `sensor_planta` (hoy se crea con `alarms: null`).
3. Provisionado desde `deploy/onboarding/tb.py` como parte del
   body del profile, o importado como JSON desde la UI de TB.

**Cuándo abordarlo:** cuando el operador tenga los umbrales reales de
la planta. Para el MVP regulatorio no bloquea — la demo se centra en
ingesta + inferencia + blockchain.

---

## Propagación a TB alarms (opcional, post-MVP)

El campo `alarm_level` del Tipo 1 se puede mapear a alarmas nativas de
TB configurando una **alarm rule** en el profile `inference_results`:

```
condition:  alarm_level >= 1
severity:   depende de alarm_level (1 → WARNING, 2 → MAJOR, 3 → CRITICAL)
clearCondition: alarm_level == 0
```

Así las alarmas del AI pasan a ser visibles en el Alarms tab de TB
junto con las del Tipo 2. Alineación semántica de severidades:

| `alarm_level` | TB severity |
|---|---|
| 0 | (no alarma) |
| 1 | `WARNING` |
| 2 | `MAJOR` |
| 3 | `CRITICAL` |

No es obligatorio para el MVP — el frontend puede leer directamente de
la timeseries del device `ai-inference-<CLIENT>` sin pasar por el
sistema de alarmas de TB.

---

## Resumen

| Tipo | Origen | Canal | Destino TB | Frontend lee de | Estado |
|---|---|---|---|---|---|
| **1. Inferencia AI** | Servicio AI | `alarm_level` en writeback | Device `ai-inference-<CLIENT>` | Timeseries del device | ✅ Contrato definido |
| **2. Sensor raw** | TB alarm rules | Profile `sensor_planta` | Alarms tab nativo | `/api/plugins/alarm/*` | 🟡 Diseño pendiente de thresholds empíricos |

Los dos tipos son independientes: el Tipo 1 funciona sin el Tipo 2 y
viceversa. Frontend puede consumir ambos en paralelo.

---

## Referencias

- [`../contracts/ai-service.md`](../contracts/ai-service.md) — contrato completo del servicio AI (inferencia NR→AI y writeback AI→TB), incluye schema con `alarm_level` / `alarm_message` (Parte 2) y §A9 sobre responsabilidad del AI en evaluar thresholds.
- [`ADR-003.md`](ADR-003.md) — decisión del pipeline v2 (NR como router, no evaluador).
