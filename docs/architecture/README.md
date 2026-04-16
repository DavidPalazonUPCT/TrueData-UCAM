# Arquitectura — TrueData

Índice de decisiones arquitectónicas (ADRs), diagrama de alto nivel
del pipeline v2, y punto de entrada a la documentación de
implementación.

---

## Diagrama de alto nivel (pipeline v2)

```
┌─────────────────────┐
│   PLC (planta)      │
│   OPC-UA server     │
└──────────┬──────────┘
           │ OPC-UA
           ▼
┌─────────────────────┐
│   Cliente OPC       │
│   (externo a UCAM)  │
└──────────┬──────────┘
           │ HTTP POST /api/opc-ingest
           │ {ts, values: {...}}
           ▼
┌─────────────────────────────────────┐
│   Node-RED                          │
│   (truedata-nodered/)               │
│                                     │
│   - Valida payload                  │
│   - Emite connect lazy por device   │
│   - Construye Gateway MQTT payload  │
│   - Dispara ML inference paralelo   │
└─────┬───────────────────┬───────────┘
      │                   │
      │ MQTT              │ HTTP POST /api/inference
      │ v1/gateway/       │ {ts, sensors: {...}}
      │   telemetry       │ (fire-and-forget, 5 s timeout)
      ▼                   ▼
┌──────────────────┐  ┌───────────────────────┐
│   ThingsBoard    │  │   Servicio ML         │
│   (truedata-     │  │   (externo a UCAM)    │
│    thingsboard/) │  │                       │
│                  │  │   - Ejecuta modelo    │
│   - Persiste     │  │   - Escribe a TB      │
│     timeseries   │  │     por su camino     │
│   - Source of    │  │   - Escribe a         │
│     truth        │  │     consumidores      │
│                  │  │     downstream        │
└──────────────────┘  └───────────────────────┘
```

Dos salidas paralelas e independientes desde NR. TB es la fuente de
verdad; el servicio ML es consumidor paralelo que gestiona sus
propios outputs.

---

## Decisiones arquitectónicas (ADRs)

| ADR | Título | Status |
|---|---|---|
| [ADR-001](ADR-001-current-pipeline.md) | Pipeline original (NR detrás de TB, 5 hops HTTP, fan-out con tokens per-sensor) | Superseded by ADR-003 para el path v2 |
| [ADR-002](ADR-002-aggregation-windows-and-sf-openquestions.md) | Ventanas de agregación y store-and-forward — preguntas abiertas | Parcialmente superseded por ADR-003 |
| [ADR-003](ADR-003.md) | Pipeline v2: NR como pre-procesador con Gateway MQTT API | Proposed; PoC Fase 0 validada |

### Motivación de v2 (resumen extraído de ADR-003 §1)

- **Jitter intra-scan:** el PLC escribe N tags por ciclo con ms de
  diferencia entre ellos. Las ventanas de agregación del pipeline v1
  degeneraban en identidad a cadencia 34 s y podían partir un scan
  en dos.
- **Fan-out con tokens:** v1 requería un diccionario de tokens
  per-sensor en NR + N peticiones HTTP por scan. v2 usa un único
  device tipo Gateway con un solo token y fan-out nativo en TB.
- **Acoplamiento con el servicio ML:** v1 obligaba al modelo a leer
  de ventanas de agregación en TB. v2 le envía el scan raw
  directamente desde NR en paralelo a la ingestión a TB.

---

## Contratos de integración

Los contratos son decisiones de diseño UCAM. Los consumidores externos
(cliente OPC, servicio ML) implementan contra ellos.

| Contrato | Para | Dirección |
|---|---|---|
| [opc-ingest](../contracts/opc-ingest.md) | Equipo del cliente OPC | Cliente OPC → NR |
| [ml-inference](../contracts/ml-inference.md) | Equipo del servicio ML | NR → Servicio ML |

---

## Implementación

El plan de implementación vivo — con PoC, fases numeradas, resultados
de validación empírica y apéndices operacionales — está en:

- **[PLAN-001](PLAN-001)** — plan de implementación v2 (ejecución por
  fases, actualmente Fase 2.2 completada)

Contenido relevante de PLAN-001:

- §Fase 0 (PoC Gateway MQTT): validación 4/4 de auto-provisioning, QoS,
  timestamps, rule chain.
- §Fase 1–2 (compose + flow NR): infra y flow core operativo.
- §Apéndice D: contratos de API en detalle con razonamiento.
- §Apéndice E: checklist ejecutable para regenerar el entorno desde
  cero.

---

## Servicios desplegados

| Directorio | Servicio | Documentación |
|---|---|---|
| [`truedata-nodered/`](../../truedata-nodered/README.md) | Node-RED (pre-procesador + router) | README del servicio |
| [`truedata-thingsboard/`](../../truedata-thingsboard/README.md) | ThingsBoard + PostgreSQL (fuente de verdad) | README del servicio |
