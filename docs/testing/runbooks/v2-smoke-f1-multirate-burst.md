# Runbook F1 — Smoke multi-rate burst (manual)

> **Tipo:** smoke test probabilístico (no assertions estrictas). Complementa la suite pytest automatizada (`tests/integration/`) cubriendo el caso **F1** del findings v2 que por naturaleza no es determinista (LIMIT-5: posibles pérdidas bajo QoS 1 + burst sub-segundo).

---

## Objetivo

Observar el comportamiento del pipeline v2 bajo un burst multi-rate realista (cadencias heterogéneas ~1 POST/s con bundles de cardinalidad variable), reportando métricas cualitativas de pérdida.

---

## Prerrequisitos

- Stack Docker arriba (`docker compose up -d`).
- Mock ML corriendo en el host (o servicio ML real reachable desde NR).
- `EXPECTED_TAGS` configurado con los tags que planea usar el burst.
- Herramienta `jq` y `curl` disponibles.

---

## Ejecución

### 1. Generar carga

Script sugerido (guardar como `/tmp/f1_burst.sh`):

```bash
#!/bin/bash
NR_URL="${NR_URL:-http://localhost:1880}"
BASE_TS=$(date +%s%3N)

# 30 heart_only (1 tag cada uno, cadencia ~1/s)
for i in $(seq 1 30); do
    TS=$((BASE_TS + i * 1000))
    curl -s -X POST "$NR_URL/api/opc-ingest" \
        -H "Content-Type: application/json" \
        -d "{\"ts\": $TS, \"values\": {\"Heart_Bit\": $i}}" > /dev/null &
done

# 6 ea_only (1 tag cada uno, cadencia ~1/5s)
for i in $(seq 1 6); do
    TS=$((BASE_TS + i * 5000))
    curl -s -X POST "$NR_URL/api/opc-ingest" \
        -H "Content-Type: application/json" \
        -d "{\"ts\": $TS, \"values\": {\"EA_1\": $((i * 100))}}" > /dev/null &
done

# 3 full_scan (27 tags cada uno, cadencia ~1/10s)
for i in $(seq 1 3); do
    TS=$((BASE_TS + i * 10000))
    # Body con 27 tags arbitrarios
    VALUES=$(jq -nc '[range(27)] | map({("TAG_" + (. | tostring)): .}) | add')
    curl -s -X POST "$NR_URL/api/opc-ingest" \
        -H "Content-Type: application/json" \
        -d "{\"ts\": $TS, \"values\": $VALUES}" > /dev/null &
done

wait
echo "Burst completado: 39 POSTs enviados (30 heart + 6 ea + 3 full)"
```

Lanzar:
```bash
chmod +x /tmp/f1_burst.sh
time /tmp/f1_burst.sh
```

### 2. Métricas a recoger

**En TB** (vía `GET /api/plugins/telemetry/DEVICE/<id>/values/timeseries`):
- Puntos persistidos para `Heart_Bit` en la ventana `[BASE_TS, BASE_TS + 35000]`. Esperado: 30.
- Puntos persistidos para `EA_1` en `[BASE_TS, BASE_TS + 35000]`. Esperado: 6.
- Puntos persistidos en `inference-input` en la misma ventana. Esperado: 39 (si EXPECTED_TAGS cubre todos los tags usados).

**En mock ML** (contador de POSTs recibidos):
- Esperado: 39 inferencias.

### 3. Criterio de aceptación

- Pérdida ≤15% en cualquiera de las tres métricas → **smoke OK** (acordado como trade-off aceptable para burst no productivo, ver FINDINGS-v2 §LIMIT-5).
- Pérdida >15% → investigar: ¿QoS 1 bajo sesión clean? ¿Pool MQTT de NR saturado? ¿Rate limit en mock ML?

### 4. Reportar

Documentar el resultado en un issue/ticket con:
- Timestamp del run.
- Pérdida observada por métrica.
- Logs relevantes de NR (`docker logs` o debug sidebar).
- Cambios en la config desde el último run (si los hay).

---

## Notas

- El régimen OPC-UA productivo es **~0,03 POSTs/s** (1 cada 34 s). Este burst ~1,3 POSTs/s está ~40× por encima — explícitamente no productivo.
- La asimetría esperada (más pérdida en heart que en full_scan) es consistente con el cuello MQTT: más mensajes pequeños son más sensibles a ACK drops bajo sesión clean (LIMIT-5).
- Si este smoke empieza a fallar recurrentemente, reconfigurar el nodo `mqtt-broker` de NR con `cleansession: false` + `reconnectPeriod: 1000` para una sesión persistente.
