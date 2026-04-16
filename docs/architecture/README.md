# Arquitectura — pipeline v2

El pipeline ingesta scans de sensores del PLC vía un servicio OPC que
postea HTTP bulk a Node-RED. Node-RED valida cada scan y lo despacha
en paralelo a ThingsBoard (persistencia vía Gateway MQTT API) y al
servicio ML de inferencia (fire-and-forget, timeout 5 s).

```
┌──────────────┐       ┌──────────────┐  MQTT ┌──────────────┐
│ servicio OPC │  HTTP │   Node-RED   │ ────► │ ThingsBoard  │
│              │ ────► │              │       │              │
└──────────────┘       └──────┬───────┘       └──────────────┘
                              │ HTTP (paralelo)
                              ▼
                       ┌──────────────┐
                       │ servicio ML  │
                       └──────────────┘
```

## Contratos de integración

- [`POST /api/opc-ingest`](../contracts/opc-ingest.md) — servicio OPC → Node-RED.
- [`POST /api/inference`](../contracts/ml-inference.md) — Node-RED → servicio ML.

## Servicios

- [Node-RED](../../truedata-nodered/README.md) — pre-procesador y router.
- [ThingsBoard](../../truedata-thingsboard/README.md) — persistencia y fuente de verdad.
