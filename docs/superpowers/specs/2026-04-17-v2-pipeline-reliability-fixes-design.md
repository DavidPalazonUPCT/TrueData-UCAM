# Spec — Correcciones de fiabilidad del pipeline v2

- **Date:** 2026-04-17
- **Tipo:** Diseño (input para plan de implementación)
- **Autor:** David Palazon (UCAM) / Claude
- **Scope:** Corregir los 3 bugs confirmados y las limitaciones 2/4 documentadas en [FINDINGS-v2-pipeline-reliability.md](../../architecture/FINDINGS-v2-pipeline-reliability.md), construir una suite de tests de integración que los cierre, y alinear los contratos públicos e internos con la implementación post-fix.

> **No reabre decisiones arquitectónicas.** ADR-001..003 y PLAN-001 siguen vigentes. Este spec ataca *implementación* y *coherencia de docs* frente a la v2 actual.

---

## 1. Objetivo

Cerrar la matriz BUG-1/2/3 + LIMIT-2/4 del findings con:

1. Cambios mínimos en `truedata-nodered/data/flows.json` (function `fn_main`) en un único commit.
2. Una suite pytest de integración de 22 casos que garantice GREEN tras el fix y detecte regresiones futuras.
3. Un runbook manual para el caso probabilístico F1 (multi-rate burst).
4. Actualización de contratos (`docs/contracts/*.md`) y docs internos (`PLAN-001.md`, `FINDINGS-v2`).

LIMIT-1 (dropout indefinido), LIMIT-3 (type change) y LIMIT-5 (pérdidas QoS bajo burst) se consolidan como asunciones/limitaciones explícitas en los contratos, no se corrigen en código.

---

## 2. Cambios en `fn_main`

### 2.1 — Orden de validación (PASO 1)

```
1. body is JSON object (no null, no array, typeof "object")     ← BUG-2
2. ts is finite number (typeof "number" && Number.isFinite)     ← refuerzo NaN
3. ts in window [now-30d .. now+5min]                            ← LIMIT-4
4. values is non-empty object (no array)                         ← BUG-1
```

### 2.2 — Forma de `flow.lastSeen`

Antes: `{tag: value}`.
Después: `{tag: {value, ts}}`.

Tres consumidores afectados:

| Punto | Cambio |
|---|---|
| Update loop | Solo actualiza si `value !== null/undefined` (LIMIT-2) **y** `ts >= prev.ts` (BUG-3) |
| Snapshot builder (PASO 3) | `snapshot[t] = lastSeen[t].value` |
| Warmup check | `expectedTags.filter(t => !(t in lastSeen))` — sin cambio (se sigue usando `in`) |
| Admin endpoint `get-expected-tags` | `t in lastSeen` — sin cambio |
| Admin endpoint `clear-expected-tags` | Sin cambio (sigue borrando entero) |

### 2.3 — Mensajes de error (rompen contrato actual)

| Antes | Después |
|---|---|
| `"ts missing or not number"` | `"body not valid JSON object"` / `"ts missing or not finite number"` / `"ts outside acceptable window (now-30d .. now+5min)"` |
| `"values missing or empty"` | `"values must be non-empty object"` |

### 2.4 — Pseudocódigo final (este JS irá como code-fence completo en el mensaje del commit `fix(nodered):`, para que el commit sea auto-contenido frente a un diff de `flows.json` ilegible)

```javascript
// PASO 1: VALIDATION
if (!msg.payload || typeof msg.payload !== "object" || Array.isArray(msg.payload)) {
    msg.statusCode = 400;
    msg.payload = { status: "error", reason: "body not valid JSON object" };
    return [null, null, msg];
}
const ts = msg.payload.ts;
const values = msg.payload.values;
if (typeof ts !== "number" || !Number.isFinite(ts)) {
    msg.statusCode = 400;
    msg.payload = { status: "error", reason: "ts missing or not finite number" };
    return [null, null, msg];
}
const now = Date.now();
if (ts < now - 30*24*3600*1000 || ts > now + 5*60*1000) {
    msg.statusCode = 400;
    msg.payload = { status: "error", reason: "ts outside acceptable window (now-30d .. now+5min)" };
    return [null, null, msg];
}
if (typeof values !== "object" || values === null || Array.isArray(values) || Object.keys(values).length === 0) {
    msg.statusCode = 400;
    msg.payload = { status: "error", reason: "values must be non-empty object" };
    return [null, null, msg];
}

// PASO 2: LOCF update (BUG-3 + LIMIT-2)
const lastSeen = flow.get("lastSeen") || {};
for (const [tag, value] of Object.entries(values)) {
    if (value === null || value === undefined) continue;
    const prev = lastSeen[tag];
    if (!prev || ts >= prev.ts) {
        lastSeen[tag] = { value: value, ts: ts };
    }
}
flow.set("lastSeen", lastSeen);

// PASO 2a: connect messages — sin cambios
// PASO 2b: raw telemetry — sin cambios

// PASO 3: snapshot builder — nueva extracción
// const snapshot = {};
// for (const t of expectedTags) snapshot[t] = lastSeen[t].value;
```

### 2.5 — Compatibilidad del state en redeploy

Si queda un `lastSeen` en flow context con forma vieja (`{tag: value}`), el siguiente bundle del mismo tag sobreescribe su entrada con la nueva forma. Para tags que no vuelvan a aparecer, `lastSeen[t].value` es `undefined` → snapshot contendría undefined → romperían warmup implícito. Mitigación: tras redeploy, ejecutar `POST /admin/clear-expected-tags` (que ya limpia `lastSeen`). Documentado en PLAN-001 §D.4.1.

---

## 3. Simulador (`simulator/opc_client_v2.py`)

### Nuevo flag `--shift-to-now`

Desplaza todos los `ts` de los bundles para que el bundle más antiguo del dump caiga en el instante de arranque del inyector. Preserva los deltas temporales relativos entre bundles.

Justificación: el dump FR_ARAGON contiene datos de 17/12/2025 (≈4 meses atrás hoy, 17/04/2026). Con LIMIT-4 (ventana `[now-30d, now+5min]`), el replay directo del dump fallaría todos los POSTs con `400 ts outside acceptable window`. El flag permite reutilizar el dump como test de integración real sin relajar el check de seguridad en NR.

Implementación (≈10 líneas en `load_bundles`):

```python
def apply_time_shift(bundles: list[Bundle], shift_ms: int) -> list[Bundle]:
    return [Bundle(ts_ms=b.ts_ms + shift_ms, values=b.values) for b in bundles]

# En run():
if args.shift_to_now and bundles:
    shift_ms = int(time.time() * 1000) - bundles[0].ts_ms
    bundles = apply_time_shift(bundles, shift_ms)
```

---

## 4. Test harness

### 4.1 — Estructura

```
tests/
├── integration/
│   ├── conftest.py                              # fixtures
│   ├── test_pipeline_v2.py                      # 22 tests
│   └── README.md                                # requisitos, ejecución
├── runbooks/
│   └── v2-smoke-f1-multirate-burst.md           # F1 manual
requirements-dev.txt                             # pytest, requests
```

### 4.2 — Fixtures (`conftest.py`)

| Fixture | Scope | Responsabilidad |
|---|---|---|
| `nr_base_url` | session | `http://localhost:1880` (override `NR_URL`) |
| `tb_base_url` | session | `http://localhost:9090` (override `TB_URL`) |
| `tb_token` | session | Login tenant → JWT; credenciales vía `TB_USER`/`TB_PASS` |
| `mock_ml` | module | `ThreadingHTTPServer` puerto 0; expone `.url`, `.received`, `.reset()` |
| `nr_admin` | function | Configura `EXPECTED_TAGS` + `ML_URL` según el test |
| `clean_state` | function, **autouse** | Pre-test: clear expected-tags + clear ml-url + `mock_ml.reset()` |
| `tb_ts_query` | session | Helper `(device, key, startTs, endTs) -> list[{ts, value}]` vía REST TB |

### 4.3 — Mock ML

`ThreadingHTTPServer` + `BaseHTTPRequestHandler` ≈25 líneas. Acepta `POST /`, lee body JSON, appendea a lista thread-safe, responde `200 {}`. Puerto aleatorio (SO). Thread daemon.

### 4.4 — Prerrequisitos

1. `docker compose up -d` (stack NR + TB arriba).
2. NR con `NR_ADMIN_ENABLED=true`.
3. Env `TB_USER`, `TB_PASS`.
4. `pip install -r requirements-dev.txt`.
5. `pytest tests/integration/ -v`.

### 4.5 — Decisiones de simplificación

- **No orquestamos Docker desde pytest**. La suite asume stack arriba (CI-ready para despliegue real).
- **Mock ML en proceso** (no container aparte).
- **TB token session-scoped** con re-auth si expira; `lastSeen` y `EXPECTED_TAGS` se limpian por-test vía admin endpoints. Los devices TB persisten (idempotencia por `(device, key, ts)` basta).

---

## 5. Catálogo de tests (22 pytest + 1 runbook)

### Bloque A — Validación defensiva (9 tests)

| Test | Qué valida | Aserción GREEN |
|---|---|---|
| A1 | `ts` ausente | `400 "ts missing or not finite number"` |
| A2 | `ts: null` | `400` |
| A3 | `ts: "string"` | `400` |
| A4 | `values` ausente | `400 "values must be non-empty object"` |
| A5 | `values: {}` | `400` |
| **A6** | **BUG-1**: `values: [{tag}]` | `400 "values must be non-empty object"` |
| **A7** | **BUG-2**: body no-JSON con CT text/plain | `400 "body not valid JSON object"` |
| **E1** | **BUG-2**: body vacío | `400 "body not valid JSON object"` |
| **E2** | **BUG-2**: body JSON con CT text/plain | `400 "body not valid JSON object"` |

### Bloque B — Comportamiento de `values` (4 tests)

| Test | Qué valida | Aserción |
|---|---|---|
| **B1** | **LIMIT-2**: `values.X = null` | `200 OK`; el tag X NO entra en `lastSeen`; snapshot a ML (tras warmup con valores válidos de todos los tags) nunca contiene `null` |
| B2 | LIMIT-3 regresión: type change | 2 bundles (float→string): ambos `200`; TB almacena ambos |
| B3 | Valor extremo (`1.79e308`) | `200 OK`, persiste en TB |
| B5 | Idempotencia TB | 2 POSTs mismo `ts`, vals distintos → TB guarda el último |

### Bloque C — Tag handling (2 tests)

| Test | Qué valida | Aserción |
|---|---|---|
| C1 | Tag fuera de EXPECTED_TAGS | Device auto-provisionado en TB; snapshot ML NO lo incluye |
| C2 | LIMIT-1 regresión: dropout | Sensor EA_1 ausente 5 bundles → snapshots mantienen último valor LOCF |

### Bloque Warmup (2 tests)

| Test | Qué valida | Aserción |
|---|---|---|
| W-partial | Gate LOCF no emite pre-warmup | ACK contiene `warmup(N/M)`; mock ML recibe 0 POSTs |
| W-full | Gate LOCF emite post-warmup | ACK contiene `emitted`; mock ML recibe 1 POST con snapshot completo |

### Bloque F — OPC-UA realistas (5 tests, F1 en runbook)

| Test | Qué valida | Aserción |
|---|---|---|
| **F2** | **BUG-3**: out-of-order arrival | 4 bundles (ts: 0, +1s, −500ms late, +2s). Snapshot final refleja val de ts=+2s, NO del late |
| F3 | Reconnect burst | 30 bundles ts=now−10min: todos persistidos en TB |
| F4 | Fragmentation | Bundles ts=T y T+20ms → 2 snapshots distintos a mock ML |
| **F5** | **LIMIT-4**: ventana de ts | `ts=0 → 400`; `ts=−1 → 400`; `ts=now+10min → 400`; `ts=now−1h → 200`; `ts=now−40d → 400` |
| F6 | Fault + recovery | Sensor 3 bundles ausente + vuelve → snapshots: val viejo durante, val nuevo al recovery |

### Runbook F1 (manual, no pytest)

`docs/testing/runbooks/v2-smoke-f1-multirate-burst.md`:
- Script: 30 `heart_only` + 6 `ea_only` + 3 `full_scan` en 30s.
- Métricas a reportar (no asserts): %msgs llegados TB, %snapshots en mock ML.
- Criterio subjetivo: pérdida ≤15% bajo burst no productivo → aceptable.

### Tests críticos (RED → GREEN con los fixes)

- **BUG-1**: A6
- **BUG-2**: A7, E1, E2
- **BUG-3**: F2
- **LIMIT-2**: B1
- **LIMIT-4**: F5

Son 7. Los 15 restantes son regresión (deben estar GREEN tanto antes como después del fix).

---

## 6. Cambios en contratos

### 6.1 — `docs/contracts/opc-ingest.md`

- **§Respuestas** — tabla de códigos 200/400 con las 4 nuevas razones.
- **§Validaciones que rechazan el POST** — tabla de los 4 checks con orden.
- **§Reglas semánticas** — dos nuevas reglas:
  - `value: null`/`undefined` = "tag ausente en el bundle" (LIMIT-2 alineado); el `200 OK` no garantiza que el valor entró al state LOCF.
  - Tipo del valor puede cambiar entre bundles del mismo tag (LIMIT-3); NR no valida, responsabilidad del consumidor ML.
- **§Asunciones** — nueva A6: `ts` debe estar en `[now-30d, now+5min]`.
- **§Casos de error operacionales** — añadir ts negativo, ts futuro lejano, CT no-JSON.

### 6.2 — `docs/contracts/ml-inference.md`

- **Nueva garantía**: `sensors` nunca contiene `null`/`undefined` (NR filtra, LIMIT-2 fix).
- **Nueva asunción**: detección de sensor dropout (LOCF stale) es responsabilidad del servicio ML (LIMIT-1). El servicio compara `ts` del snapshot contra último punto en TB raw; si gap > N windows, emite `status: "degraded"` en writeback.
- **Nueva asunción**: tipo de `sensors[tag]` puede cambiar entre inferencias (LIMIT-3); ML debe hacer sanity-check.

### 6.3 — `docs/contracts/ml-writeback.md`

- Añadir opción: campo `status: "ok" | "degraded"` para señalizar dropout desde el ML (mitiga LIMIT-1 sin acoplar NR).

### 6.4 — `docs/architecture/PLAN-001.md` (interno)

- **§D.4** — actualizar pseudocódigo con el nuevo orden de validación y la nueva forma de `lastSeen`.
- **§D.4.1** — nueva nota operacional: LIMIT-4 ventana y razón; compat del state en redeploy.

### 6.5 — `docs/architecture/FINDINGS-v2-pipeline-reliability.md` (interno)

- **§9 Historial** — entrada fechada: BUG-1/2/3 + LIMIT-2/4 corregidos y validados con suite pytest; LIMIT-1/3/5 consolidados en contratos.

---

## 7. Secuencia de commits (7 commits)

| # | Commit | Archivos principales | Estado tras commit |
|---|---|---|---|
| 1 | `chore(tests): añadir harness de integración v2` | `tests/integration/conftest.py`, `tests/integration/README.md`, `requirements-dev.txt` | Infra lista |
| 2 | `test(integration): suite de regresión v2 (Grupos A/B/C/E/F2-F6, 22 casos, RED antes del fix)` | `tests/integration/test_pipeline_v2.py` | **RED**: 7 críticos fallan, 15 pasan |
| 3 | `feat(simulator): añadir flag --shift-to-now para replay de dumps históricos` | `simulator/opc_client_v2.py` | Dump FR_ARAGON replayeable |
| 4 | `fix(nodered): corregir BUG-1/2/3 + LIMIT-2/4 en fn_main` | `truedata-nodered/data/flows.json` | **GREEN**: 22/22. Mensaje incluye el JS final completo como code-fence (diff de `flows.json` ilegible) |
| 5 | `docs(contracts): alinear opc-ingest + ml-inference + ml-writeback con v2 post-fix` | 3 docs de `docs/contracts/` | Contratos alineados |
| 6 | `docs(architecture): actualizar PLAN-001 §D.4 y cerrar FINDINGS-v2` | `PLAN-001.md`, `FINDINGS-v2-pipeline-reliability.md` | Docs internos alineados |
| 7 | `docs(testing): añadir runbook F1 multi-rate burst` | `docs/testing/runbooks/v2-smoke-f1-multirate-burst.md` | Runbook disponible |

---

## 8. Criterios de éxito (cierre de sesión)

1. `pytest tests/integration/ -v` → **22/22 GREEN** contra stack real (NR + TB + mock_ml).
2. Runbook F1 ejecutado y reportado cualitativamente (pérdida ≤15% aceptable).
3. `rtk git log --oneline main` muestra los 7 commits en orden.
4. Contratos publicables (`docs/contracts/*.md`) reflejan comportamiento real verificado.

---

## 9. Fuera de scope (explícito)

- LIMIT-1 (dropout stale counter en NR): trade-off consciente; mitigación vía contrato ML.
- LIMIT-3 (type change validation): responsabilidad consumidor ML; documentado.
- LIMIT-5 (MQTT QoS 1 pérdidas bajo burst): documentado; validación bajo régimen real diferida al deployment contra servicio ML real.
- Portado a CI: harness asume stack local arriba; no hay GitHub Actions / GitLab CI en esta sesión.
- Autenticación en `/api/opc-ingest`: sigue como A5 en opc-ingest.md (decisión temporal).

---

## 10. Referencias

- [FINDINGS-v2-pipeline-reliability.md](../../architecture/FINDINGS-v2-pipeline-reliability.md)
- [PLAN-001.md §D.4](../../architecture/PLAN-001.md)
- [ADR-003.md](../../architecture/ADR-003.md)
- [opc-ingest.md](../../contracts/opc-ingest.md)
- [ml-inference.md](../../contracts/ml-inference.md)
- [ml-writeback.md](../../contracts/ml-writeback.md)
