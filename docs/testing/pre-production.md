# Pre-production testing

Plan de validación antes de llevar el stack a la demo / producción. Cubre
regresión automática (pytest) y tests manuales con datos reales (simulador).

**Prerrequisito común:** stack arriba (onboarding ejecutado, TB y NR healthy).
Ver [`../SETUP.md`](../SETUP.md).

---

## 1. Regresión automática — 10 s

```sh
pip install -r requirements.txt
export TB_USER=tenant@thingsboard.org TB_PASS=tenant
pytest tests/integration/ -v
```

**Pass:** 26 passed. Cubre validación defensiva del endpoint, LOCF, warmup,
idempotencia TB, ventana de timestamps, null handling y out-of-order.

---

## 2. Smoke con datos reales — 5 s

Primer test tras el bring-up: valida que el contrato real del OPC Client
fluye E2E con el dump de FR_ARAGON.

```sh
export SQL=src/FR_ARAGON/Francisco_16_01_2026.sql
export NR=http://localhost:1880/api/opc-ingest

python3 simulator/opc_client_v2.py --sql $SQL --url $NR \
    --rate burst --shift-to-now --limit 10
```

**Pass:** `exit=0`, `Errors: 0`. En TB aparecen devices nuevos (uno por tag,
hasta 27) con profile `sensor_planta`:

```sh
JWT=$(curl -s -X POST http://localhost:9090/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"tenant@thingsboard.org","password":"tenant"}' | jq -r .token)
curl -s "http://localhost:9090/api/tenant/devices?pageSize=100&page=0" \
    -H "X-Authorization: Bearer $JWT" \
    | jq -r '.data[] | select(.type=="sensor_planta") | .name' | wc -l
```

---

## 3. Escenarios extendidos del simulador

Seis regímenes para cubrir distintas dimensiones del pipeline. Ejecutar el
que interese según lo que quieras validar.

| # | Régimen | Duración | `--rate` | `--limit` | `--shift` | Propósito |
|---|---|---|---|---|---|---|
| A | Dry-run | 5 s | — | 5 | — | Inspeccionar estructura del dump, cero side-effects |
| B | Burst full | 3-8 min | `burst` | — | `--shift-to-now` | Stress: ~20.8k POSTs consecutivos |
| C | Real-time | 50-60 min | `1.0` | 100 | `--shift-to-now` | Cadencia PLC real (~30-35 s/bundle) |
| D | Acelerado 100× | 5-8 min | `100` | 1000 | `--shift-to-now` | Forma del tráfico sin esperar horas |
| E | Ventana LIMIT-4 | 5 s | `burst` | 5 | — (off) | Test **negativo**: ts fuera de ventana → 400 |
| F | Demo en vivo | ~10 min | mixto | 100+20 | `--shift-to-now` | Burst inicial + real-time en dashboard |

### A. Dry-run

```sh
python3 simulator/opc_client_v2.py --sql $SQL --dry-run --limit 5
```
Imprime 3 bundles JSON en stdout + distribución de cardinalidad en stderr.
**Pass:** `exit=0`, JSON válido, ningún device nuevo en TB.

### B. Burst full

```sh
python3 simulator/opc_client_v2.py --sql $SQL --url $NR --rate burst --shift-to-now
```
**Pass:** `exit=0`, `Errors < 1 %` (~200 fallos sobre 20k es el techo
aceptable — ver LIMIT-5). Stats finales muestran `~60-70 bundles/s`. La
cardinality distribution cuadra con el patrón bimodal (mayoría 27 tags,
minoría 1-2 de CoV events).

**Fail típico:** `Errors > 5 %` indica saturación del pool MQTT de NR.

### C. Real-time

```sh
python3 simulator/opc_client_v2.py --sql $SQL --url $NR --rate 1.0 --shift-to-now --limit 100
```
Reproduce los deltas temporales originales del PLC. Los primeros bundles
responden con `"inference":"warmup(N/N)"` hasta completar la primera full
scan; desde ahí `"inference":"emitted"`.

**Pass:** `exit=0`, `Errors: 0`, Duration ≈ suma real de deltas ±5 %.

### D. Acelerado 100×

```sh
python3 simulator/opc_client_v2.py --sql $SQL --url $NR --rate 100 --shift-to-now --limit 1000 -v
```
**Pass:** `exit=0`, `Errors: 0`, Duration ≈ (deltas_reales / 100).
Si sube `Errors`, bajar a `--rate 50` o `--rate 10`.

### E. Ventana de validación (test negativo)

```sh
python3 simulator/opc_client_v2.py --sql $SQL --url $NR --rate burst --limit 5
```
Sin `--shift-to-now`, los `ts` del dump (2025-12) caen fuera de la ventana
`[now-30d, now+5min]`.

**Pass:** `exit=1`, los 5 POSTs devuelven `400` con
`"reason":"ts outside acceptable window (now-30d .. now+5min)"`. **Ninguna**
telemetría nueva en TB.

### F. Demo en vivo

```sh
# Burst inicial (historia reciente)
python3 simulator/opc_client_v2.py --sql $SQL --url $NR --rate burst --shift-to-now --limit 100

# Continuación en tiempo real
python3 simulator/opc_client_v2.py --sql $SQL --url $NR --rate 1.0 --shift-to-now --limit 20 -v
```
En la UI de TB (`http://localhost:9090` → Device Groups → sensor_planta) los
timeseries se actualizan en vivo tras el burst inicial.

---

## 4. Smoke F1 multi-rate burst (probabilístico)

Complementa la suite automatizada cubriendo LIMIT-5 (posibles pérdidas bajo
QoS 1 + burst sub-segundo). **Probabilístico:** no hay assertions estrictas.

```bash
NR_URL="${NR_URL:-http://localhost:1880}"
BASE_TS=$(date +%s%3N)

# 30 heart_only (cadencia ~1/s)
for i in $(seq 1 30); do
  curl -s -X POST "$NR_URL/api/opc-ingest" \
    -H "Content-Type: application/json" \
    -d "{\"ts\": $((BASE_TS + i*1000)), \"values\": {\"Heart_Bit\": $i}}" > /dev/null &
done
# 6 ea_only (cadencia ~1/5s)
for i in $(seq 1 6); do
  curl -s -X POST "$NR_URL/api/opc-ingest" \
    -H "Content-Type: application/json" \
    -d "{\"ts\": $((BASE_TS + i*5000)), \"values\": {\"EA_1\": $((i*100))}}" > /dev/null &
done
# 3 full_scan (27 tags, cadencia ~1/10s)
for i in $(seq 1 3); do
  VALUES=$(jq -nc '[range(27)] | map({("TAG_"+(.|tostring)): .}) | add')
  curl -s -X POST "$NR_URL/api/opc-ingest" \
    -H "Content-Type: application/json" \
    -d "{\"ts\": $((BASE_TS + i*10000)), \"values\": $VALUES}" > /dev/null &
done
wait
```

**Verificar en TB** (puntos persistidos en la ventana `[BASE_TS, BASE_TS+35000]`):
- `Heart_Bit`: esperado 30
- `EA_1`: esperado 6
- `inference-input`: esperado 39 (si `EXPECTED_TAGS` cubre todos)

**Pass:** pérdida ≤ 15 % en cualquiera de las métricas.
**Fail:** pérdida > 15 % → investigar QoS 1 bajo clean-session, pool MQTT
saturado, o rate limit en el servicio AI/mock.

**Nota de contexto:** el régimen OPC-UA productivo es ~0,03 POSTs/s (1 cada
34 s). Este burst va ~40× por encima — explícitamente no productivo. Si el
smoke falla de forma recurrente, reconfigurar `broker_tb` con
`cleansession: false` + `reconnectPeriod: 1000`.

---

## Debug tips

- **Ver qué tags trae el dump:**
  ```sh
  python3 simulator/opc_client_v2.py --sql $SQL --dry-run --limit 1 | jq -r '.values | keys[]'
  ```
- **Distribución de cardinalidad:** el simulador la imprime en stderr al
  cargar el SQL, antes de cualquier POST.
- **Bundle específico por `ts`:** `--limit N` + `-v` muestra cada POST con
  su `ts` y cardinalidad.
- **Stats parciales:** `Ctrl+C` imprime las stats del trabajo hecho.
