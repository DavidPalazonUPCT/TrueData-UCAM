# Spec — `onboard_client_v2.py` (pipeline v2 de provisioning de clientes)

- **Date:** 2026-04-17
- **Autor:** David Palazon (UCAM) / Claude
- **Tipo:** Design spec (entrada para writing-plans)
- **Scope:** Sustituir el script ad-hoc `/tmp/fase3_exec.py` usado en Fase 3 por un pipeline de onboarding reproducible e idempotente. MVP para presentación a INCIBE, deploy in-place en PC embebido, velocidad > perfección.
- **Relacionado:** [docs/operations/client-provisioning.md](../../operations/client-provisioning.md) · [PLAN-001 §Fase 3](../../architecture/PLAN-001.md) · [ADR-003](../../architecture/ADR-003.md) · [ml-writeback.md](../../contracts/ml-writeback.md) · [airtrace-writeback.md](../../contracts/airtrace-writeback.md) · [opc-ingest.md](../../contracts/opc-ingest.md)

---

## 1. Contexto y problema

### 1.1 Estado actual (gap a cerrar)

Durante la ejecución de Fase 3 del PLAN-001 se provisionaron en TB los recursos que v2 necesita para FR_ARAGON mediante un script ad-hoc (`/tmp/fase3_exec.py`, ~180 líneas). El script:

- Hardcodea `TB=http://localhost:9090`, `CLIENT=FR_ARAGON`, credenciales admin.
- Crea 4 profiles + 2 devices de writeback idempotentemente (patrón `ensure_X`).
- Ejecuta smoke tests básicos (POST + GET verify).
- **No configura NR** — los endpoints `/admin/set-expected-tags` y `/admin/set-ml-url` se llamaron a mano con curl durante la fase.
- **Escupe tokens a stdout** — no hay fichero entregable.
- **No está committeado** — vive en `/tmp/`, se pierde con reboot.

Si hoy tuviéramos que onboardear un segundo cliente (EDAR_MURCIA, ESAMUR en v2, …), habría que reescribir el script de memoria, ejecutar curl a mano para NR y copiar tokens de stdout a un canal seguro. No hay single-source-of-truth ni reproducibilidad.

El doc operacional [client-provisioning.md](../../operations/client-provisioning.md) describe el flujo propuesto a alto nivel. Este spec lo concreta en nivel de diseño suficiente para generar un plan de implementación.

### 1.2 Requisitos explícitos del usuario

Del brainstorming (2026-04-17):

1. **Cercano a lo existente pero mejorado y fiable.** Mínima desviación del patrón del ad-hoc; mejoras medibles (parametrización, configuración NR, fichero entregable, smoke tests integrados).
2. **"Conexión sencilla" para servicios externos.** ML y airtrace deben poder consumir el token con cero glue code.
3. **Todo el sistema corre en local** (PC embebido). La configuración inicial se hace desde ese mismo host. Sin CI, sin deploys remotos.
4. **Plataforma single-tenant.** Un stack = un cliente. No hay multi-tenant dentro de un TB.
5. **Orden de arranque del docker-compose:** core (TB+NR+OPC) → onboarding → servicios externos (ML, blockchain-api).
6. **MVP para INCIBE.** Velocidad de implementación > perfección técnica. Calidad casi-producción en el happy path, no defensiva paranoica.

---

## 2. Goals y Non-goals

### Goals

- G1. Producir un script CLI Python self-contained (`deploy/onboard_client_v2.py`) que, dado un manifest YAML y env vars mínimas, deje el stack listo para que los servicios externos se conecten.
- G2. Idempotencia real — re-ejecutar converge sin duplicar ni corromper.
- G3. Fail-fast con exit codes categorizados (sin rollback; re-ejecución manual del operador).
- G4. Salida de ficheros `.env` per-servicio en `deploy/secrets/<CLIENT>/` compatibles con Docker `env_file:`.
- G5. Coexistencia con el pipeline v1 legacy (`env_client.py` y scripts numerados) sin modificarlo.

### Non-goals (fuera del scope de este spec)

- **N1. Rotación programada de tokens.** El flag `--force` rota en demanda; un script `rotate_token.py` dedicado es trabajo posterior (doc operacional §7.3).
- **N2. Offboarding de clientes.** Script `offboard_client.py` con retención histórica es trabajo posterior (§8 del doc operacional).
- **N3. Integración con secret manager real** (Vault, 1Password API, AWS SM). File-based `.env` es suficiente para MVP; integración puede añadirse después leyendo de un backend pluggable.
- **N4. Configurar servicios externos** (ML, airtrace). El onboarding solo toca core (TB+NR). Los servicios externos consumen artefactos.
- **N5. Migrar clientes v1 a v2.** ESAMUR sigue con `env_client.py` hasta que se complete PLAN-001 Fase 4 para ese cliente.
- **N6. Multi-tenant en un solo TB.** Plataforma es single-tenant por diseño.
- **N7. Suite pytest automatizada.** Testing procedural manual suficiente para MVP. pytest/CI son trabajo futuro si/cuando el deploy lo requiera.
- **N8. Proyección al monorepo TRUEDATA GitLab.** El script es lo bastante simple para portarse mecánicamente más tarde si hay contribución — no optimizamos el diseño para ese escenario ahora.

---

## 3. Decisiones resumidas

| # | Decisión | Justificación |
|---|---|---|
| D1 | Alcance = solo core (TB+NR) | Servicios externos consumen artefactos; contratos ml/airtrace-writeback §A6 exigen token out-of-band |
| D2 | CLI Python monolítico single-file | Cercanía al ad-hoc; trivial de containerizar después |
| D3 | Manifest YAML client-specific committeado | Declarativo, diff-friendly, schema-validable; una fuente por cliente |
| D4 | Credenciales admin vía env vars root `.env` | Convención Docker compose estándar; cero ficheros JSON per-client gitignoreados |
| D5 | Secrets = `.env` per-servicio | Compatibles con Docker `env_file:`; separación host/token para rotación limpia |
| D6 | Exit codes categorizados (0/1/2/3/4) | Permite retry policies en orquestadores futuros |
| D7 | Idempotencia por comparación de nombre (profiles/devices) | Ya probado en ad-hoc; robusto frente a auto-provisioning por NR |
| D8 | Fail-fast sin rollback; re-ejecución resuelve parciales | Simplicidad > transacciones; idempotencia lo hace seguro |
| D9 | Testing procedural manual + runtime smoke (sin pytest ni CI) | MVP; velocidad > completitud |
| D10 | Script no importa `APIThingsboard.py` del v1 | v1 es legacy; ciclos de vida independientes |

---

## 4. Arquitectura y layout

### 4.1 Ubicación en el repo UCAM (donde se desarrolla hoy)

```
deploy/
├── onboard_client_v2.py              [NEW]   ← CLI monolítico (~400-500 líneas)
├── clients/                           [NEW]   ← repositorio de manifests (commit)
│   └── FR_ARAGON.yaml                 [NEW]   ← primer manifest (migrado del ad-hoc)
├── secrets/                           [NEW]   ← gitignored, mode 0700
│   └── FR_ARAGON/                     (creado al ejecutar)
│       ├── ml-inference.env           (mode 0600)
│       └── airtrace-anchor.env        (mode 0600)
│
├── env_client.py                      [UNCHANGED]  ← v1 legacy, sirve ESAMUR v1
├── 1_*.py  2_*.py  3_*.py  4_*.py     [UNCHANGED]
├── APIThingsboard.py                  [UNCHANGED]  ← NO importado por v2
├── Client.json  ESAMUR/  Plantillas/  [UNCHANGED]
```

Cambios globales:
- `.gitignore` raíz: añadir `deploy/secrets/`.

### 4.2 Cómo se invoca en la máquina embebida

El stack se levanta en el PC embebido con un `docker-compose.yml` local. El onboarding se ejecuta **desde el host** tras core healthy y antes de arrancar servicios externos:

```bash
# 1. Core up
docker compose up -d thingsboard node-red opc-client
# (esperar healthchecks)

# 2. Onboarding (CLI desde el host, contra los contenedores)
export TB_ADMIN_PASSWORD='...'
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml

# 3. Servicios externos (consumen deploy/secrets/FR_ARAGON/*.env via env_file)
docker compose up -d ml-classical blockchain-api
```

Los servicios externos consumen los `.env` vía la directiva `env_file:` del docker-compose:

```yaml
ml-classical:
  env_file: ./deploy/secrets/FR_ARAGON/ml-inference.env
blockchain-api:
  env_file: ./deploy/secrets/FR_ARAGON/airtrace-anchor.env
```

Docker inyecta los `CLAVE=valor` como env vars en container-create time. El código de cada servicio hace `os.environ["TB_DEVICE_TOKEN"]` — cero glue.

Definición del servicio `onboarding` como servicio del compose (opcional, para one-command startup) queda fuera del scope de este spec.

---

## 5. Manifest schema

**Fichero:** `deploy/clients/<CLIENT>.yaml`. Inline, auto-contenido, sin referencias externas.

```yaml
# deploy/clients/FR_ARAGON.yaml
client:
  id: FR_ARAGON                                # [required]  regex ^[A-Z0-9_]+$  usado en device names
  name: "EDAR Francisco (Aragón)"              # [required]  human-readable
  description: "Planta piloto v2"              # [optional]  free text

sensors:
  expected_tags:                               # [required]  non-empty, sin duplicados
    - ERROR_COMM
    - Q_SALIDA_D1
    - Q_SALIDA_D2
    # ... 27 tags para FR_ARAGON
    - EA_4

ml_inference:
  url: http://ml-classical:5000/api/inference  # [optional]  null/omitido ⇒ NR con ML silenciado (clear-ml-url)
```

**Validación al cargar (antes de cualquier llamada de red):**

| Campo | Regla |
|---|---|
| `client.id` | `^[A-Z0-9_]+$`, 3-32 caracteres |
| `client.name` | string no vacío |
| `sensors.expected_tags` | lista de 1..200 strings únicos, cada uno `^[A-Za-z0-9_]+$` |
| `ml_inference.url` | si presente: `^https?://` |

Fallo de validación → exit 2, no toca TB/NR.

**Campos deliberadamente ausentes (YAGNI):**
- `airtrace.enabled` — siempre se provisiona el device `airtrace-anchor-<CLIENT>`; coste ~0.
- `thingsboard_url` / `nodered_url` — propiedades del entorno, no del cliente; van por env var.
- `airtrace.endpoint` / `chain_id` — informativos, viven en `airtrace-writeback.md`.
- Expansión `${VAR}` en YAML — complejidad sin beneficio; env vars directos al script.

---

## 6. Contrato CLI + env vars

### 6.1 Signature

```
python3 deploy/onboard_client_v2.py --manifest <PATH> [--dry-run] [--force] [-v]
```

### 6.2 Flags

| Flag | Obligatorio | Efecto |
|---|---|---|
| `--manifest <PATH>` | sí | Ruta al YAML del cliente |
| `--dry-run` | no | Valida manifest, login TB + ping NR, imprime plan, no escribe nada |
| `--force` | no | Rota tokens de devices existentes (regenera credentials en TB) |
| `-v` / `--verbose` | no | Loggea cada request HTTP |

### 6.3 Env vars

| Variable | Default | Fuente esperada |
|---|---|---|
| `TB_URL` | `http://localhost:9090` | `.env` raíz o export manual |
| `TB_ADMIN_USER` | `tenant@thingsboard.org` | Igual |
| `TB_ADMIN_PASSWORD` | *(sin default — exit 2 si falta)* | `.env` raíz, nunca committeada |
| `NR_URL` | `http://localhost:1880` | Igual |

**Nota:** `9090`/`1880` son los puertos del stack UCAM actual. Si el deploy cambia de puertos, se sobrescribe con env vars sin tocar código.

### 6.4 Exit codes

| Code | Clase | Ejemplos |
|---|---|---|
| `0` | OK | Onboarding completo, secrets escritos |
| `1` | Error inesperado | Excepción Python no capturada |
| `2` | Input inválido | Manifest ausente/inválido, env var requerida missing |
| `3` | Sistema externo | TB/NR unreachable, auth failure, HTTP 4xx/5xx |
| `4` | Smoke test failed | TB aceptó POST pero GET no devuelve la key esperada |

### 6.5 Output stdout

Prefijos deterministas: `[✓]` creado, `[=]` existía, `[↻]` rotado con `--force`, `[✗]` fallo.

Ejemplo modo normal (happy path):
```
[✓] manifest: deploy/clients/FR_ARAGON.yaml (client=FR_ARAGON, 27 tags)
[✓] TB login: http://localhost:9090 (user=tenant@thingsboard.org)
[=] profile sensor_planta           existed  id=b2e7ce20-...
[=] profile inference_input         existed  id=2de80d60-...
[✓] profile inference_results       created  id=5ac95d20-...
[✓] profile blockchain_anchor       created  id=5ace1810-...
[✓] device  ml-inference-FR_ARAGON      created  token=KpUS...7R
[✓] device  airtrace-anchor-FR_ARAGON   created  token=XtTp...WD
[✓] NR configured:   EXPECTED_TAGS=[27 tags], ML_INFERENCE_URL=<set>
[✓] smoke tests:     ML 200 OK (score persisted), airtrace 200 OK (tx_hash persisted)
[✓] secrets written: deploy/secrets/FR_ARAGON/ml-inference.env (0600)
[✓] secrets written: deploy/secrets/FR_ARAGON/airtrace-anchor.env (0600)

onboarding complete. servicios ML y blockchain-api pueden arrancar (env_file apunta a deploy/secrets/FR_ARAGON/).
```

Ejemplo modo `--dry-run`:
```
[dry-run] manifest: deploy/clients/FR_ARAGON.yaml (valid)
[dry-run] TB login: http://localhost:9090 OK
[dry-run] NR ping:  http://localhost:1880 OK
[dry-run] would create: profile inference_results, profile blockchain_anchor
[dry-run] would create: device ml-inference-FR_ARAGON, device airtrace-anchor-FR_ARAGON
[dry-run] would configure NR: set-expected-tags (27), set-ml-url
[dry-run] would write: deploy/secrets/FR_ARAGON/*.env

no side effects performed. run without --dry-run to apply.
```

---

## 7. Flujo de ejecución (7 fases ordenadas)

### Fase 1 — Cargar + validar manifest
- Lee YAML, valida schema (§5).
- Construye diccionario interno normalizado.
- Fallo → exit 2, no toca nada.

### Fase 2 — Leer env vars + login TB
- Lee `TB_URL`, `TB_ADMIN_USER`, `TB_ADMIN_PASSWORD`, `NR_URL`.
- `POST {TB_URL}/api/auth/login` → JWT.
- `TB_ADMIN_PASSWORD` falta → exit 2.
- TB unreachable / 401 → exit 3.

### Fase 3 — Asegurar 4 profiles (idempotente)

Lista: `[sensor_planta, inference_input, inference_results, blockchain_anchor]`.

Para cada profile:
1. `GET /api/deviceProfiles?pageSize=100&page=0` con `X-Authorization: Bearer <JWT>`.
2. Si `name` aparece → `[=]`, continúa.
3. Si no → `POST /api/deviceProfile` con body completo (ver PLAN-001 §Fase 3 nota 1):
   ```json
   {
     "name": "inference_results",
     "type": "DEFAULT",
     "transportType": "DEFAULT",
     "provisionType": "DISABLED",
     "description": "...",
     "profileData": {
       "configuration": {"type": "DEFAULT"},
       "transportConfiguration": {"type": "DEFAULT"},
       "provisionConfiguration": {"type": "DISABLED", "provisionDeviceSecret": null},
       "alarms": null
     }
   }
   ```
4. Error HTTP → exit 3.

### Fase 4 — Asegurar 2 devices de writeback + capturar tokens

Devices: `ml-inference-<CLIENT>` (profile `inference_results`), `airtrace-anchor-<CLIENT>` (profile `blockchain_anchor`).

Por cada uno:
1. `GET /api/tenant/devices?deviceName=<NAME>` — verifica existencia.
2. Existe y no `--force` → `GET /api/device/<id>/credentials` → token, `[=]`.
3. Existe y `--force` → `POST /api/device/<id>/credentials` regenerado → token nuevo, `[↻]`.
4. No existe → `POST /api/device` + `GET .../credentials`, `[✓]`.

Tokens se guardan en memoria; aún no se escriben a disco.

### Fase 5 — Configurar Node-RED

1. `POST {NR_URL}/admin/set-expected-tags` body `{tags: [...]}` desde `manifest.sensors.expected_tags`.
2. Si `manifest.ml_inference.url` presente: `POST {NR_URL}/admin/set-ml-url` body `{url: "..."}`.
3. Si omitido/null: `POST {NR_URL}/admin/clear-ml-url`.

Ambos endpoints son overwrites idempotentes. NR unreachable o `!= 200` → exit 3.

### Fase 6 — Smoke tests

Genera `scan_ts = int(time.time() * 1000)`. Para cada writeback:
1. `POST /api/v1/<TOKEN>/telemetry` con body sintético (ver `/tmp/fase3_exec.py` §3.7 estructura).
2. `sleep(1)` para que la rule chain persista.
3. `GET /api/plugins/telemetry/DEVICE/<id>/values/timeseries?keys=<csv>&startTs=<scan_ts-1>&endTs=<scan_ts+1>&limit=1`.
4. Verifica que cada key esperada tiene un punto.

Key ausente → exit 4. **No se escriben secrets.**

### Fase 7 — Escribir secrets

- `mkdir -p deploy/secrets/<CLIENT>/` con mode `0700` (si existe con permisos laxos, se endurece).
- Escribe `ml-inference.env` y `airtrace-anchor.env` con mode `0600`.
- Siempre reescribe (sin merge con previous).
- Imprime summary final y exit 0.

### Propiedades del flujo

- **Atomicidad:** ninguna por fase única. Fallos parciales se resuelven por re-ejecución (idempotencia).
- **Sin rollback:** operador diagnostica, corrige, re-ejecuta.
- **Sin concurrencia:** asume invocación serial (single-tenant + one-shot).
- **Observabilidad:** stdout determinista, exit codes categorizados.

---

## 8. Formato de los ficheros de secrets

### 8.1 Directorio

`deploy/secrets/<CLIENT>/` mode `0700`. El script lo crea si falta, endurece permisos si laxos.

### 8.2 `ml-inference.env` (mode `0600`)

```env
# onboard_client_v2.py — generated 2026-04-17T15:30:42Z
# DO NOT EDIT MANUALLY. Regenerate via deploy/onboard_client_v2.py.
# Deliver this file to the ML service team via secure channel.
CLIENT=FR_ARAGON
TB_HOST=http://localhost:9090
TB_DEVICE_NAME=ml-inference-FR_ARAGON
TB_DEVICE_TOKEN=KpUSuPtmAbpTXclY107R
```

### 8.3 `airtrace-anchor.env` (mode `0600`)

```env
# onboard_client_v2.py — generated 2026-04-17T15:30:42Z
# DO NOT EDIT MANUALLY. Regenerate via deploy/onboard_client_v2.py.
# Deliver this file to the airtrace service team via secure channel.
CLIENT=FR_ARAGON
TB_HOST=http://localhost:9090
TB_DEVICE_NAME=airtrace-anchor-FR_ARAGON
TB_DEVICE_TOKEN=XtTpOplpo9pOKXovATWD
```

### 8.4 Campos y justificación

| Campo | Razón |
|---|---|
| Header timestamp UTC | Auditabilidad |
| `CLIENT` | Tag para métricas/logs del servicio consumidor |
| `TB_HOST` | URL base; servicio compone `${TB_HOST}/api/v1/${TB_DEVICE_TOKEN}/telemetry` |
| `TB_DEVICE_NAME` | Debugging bilateral UCAM ↔ consumidor |
| `TB_DEVICE_TOKEN` | Credencial. **Único campo sensible.** Una sola línea cambia en rotación |

**Decisión:** no mezclar host+token en un único `TB_WRITEBACK_URL`. Facilita rotación y reduce exposición en logs que impriman la URL.

### 8.5 Semántica de re-escritura

- Sin `--force`: mismos valores, timestamp actualizado.
- Con `--force`: token nuevo; viejo queda invalidado atómicamente en TB.
- **Nunca** se hace merge con contenido previo — siempre overwrite.
- El estado canónico vive en TB. Borrar `deploy/secrets/` es recuperable con `--force` + re-run.

### 8.6 Consumo por servicios downstream

Deploy in-place en el mismo PC embebido — Docker compose directiva `env_file:`:
```yaml
services:
  ml-classical:
    env_file:
      - ./deploy/secrets/FR_ARAGON/ml-inference.env
  blockchain-api:
    env_file:
      - ./deploy/secrets/FR_ARAGON/airtrace-anchor.env
```

Docker inyecta los `CLAVE=valor` como env vars del contenedor en container-create time. El código del servicio hace `os.environ["TB_DEVICE_TOKEN"]` — cero glue.

---

## 9. Manejo de errores

### Política

**Fail-fast, no rollback, no retries internos.** Cualquier error → exit code categorizado + stdout claro. Operador diagnostica, corrige, re-ejecuta. La idempotencia de Fases 3-4 y la naturaleza overwrite de Fases 5-7 garantizan convergencia desde cualquier estado parcial.

Retries a nivel de orquestador (docker-compose `restart_policy`) si el entorno lo requiere — no en el script.

### Modos de fallo (por fase)

| Fase | Síntoma típico | Exit | Acción del operador |
|---|---|---|---|
| 1 | Schema inválido en manifest | 2 | Corregir YAML |
| 1 | Manifest path no existe | 2 | Corregir `--manifest` |
| 2 | `TB_ADMIN_PASSWORD` no seteada | 2 | Exportar la env var |
| 2 | TB login 401 | 3 | Verificar password |
| 2 | TB unreachable | 3 | Verificar stack arriba + `TB_URL` |
| 3 | POST profile 500 NPE | 3 | Reportar (no debería pasar con body completo) |
| 4 | Profile borrado entre fases | 3 | Re-ejecutar (Fase 3 lo recrea) |
| 5 | NR unreachable / 400 / 500 | 3 | Verificar NR + flow deployed |
| 6 | Smoke test key missing | 4 | Inspeccionar rule chain del profile |
| 7 | Permission denied en write | 1 | Verificar ownership `deploy/secrets/` |

### Estados parciales

Ejemplo: falla Fase 5 tras 3-4 OK. Tras fix NR, re-ejecución:
- Fase 3: `[=]` × 4 (profiles ya existen)
- Fase 4: `[=]` × 2 (tokens reusados)
- Fase 5: ahora OK
- Fases 6-7: proceden

Tokens son idempotentes frente a re-run (TB los persiste; solo `--force` regenera).

### Fuera de scope de manejo

- Race con auto-provisioning de NR: mitigado por re-ejecución.
- Rotación de password admin durante ejecución: muy improbable; mitigado por re-ejecución.
- TB down mid-run: exit 3, operador restart + re-ejecuta.

No añadimos lógica defensiva para escenarios bizantinos — la re-ejecución los cubre sin deuda de código.

---

## 10. Testing strategy

MVP + deploy in-place local → testing procedural manual, sin framework ni CI.

### Runtime smoke test (automatizado, integrado al flow)

Fase 6 del propio script cubre el pipeline POST → rule chain → ts_kv → GET. Un `deploy/secrets/<CLIENT>/` válido implica que ese pipeline funcionó en la última ejecución. **Es el test más importante y ya es parte del script.**

### Testing Instructions en `deploy/README.md`

Sección con pasos copy-pasteables:

1. **Prerequisites** — TB + NR healthy, `TB_ADMIN_PASSWORD` exported.
2. **Dry-run** — `python3 deploy/onboard_client_v2.py --manifest ... --dry-run` → exit 0, no files created.
3. **Happy path** — mismo sin `--dry-run` → exit 0, `.env` files mode 0600.
4. **Idempotency** — re-run inmediato → `[=]` en todos los pasos; tokens unchanged.
5. **Verify TB state** — curl + JWT → lista profiles contiene los 4.
6. **Verify NR state** — `GET /admin/get-expected-tags` → lista de tags coincide con manifest.
7. **Force rotation** — `--force` → token nuevo; viejo responde 401.

Estos pasos son la suite de aceptación del MVP — se ejecutan a mano antes de demos/entregables.

### Lo que NO añadimos

- pytest / unittest / framework de tests automatizado.
- `.gitlab-ci.yml` / GitHub Actions / cualquier CI.
- Fixtures mockeadas de TB.
- Testcontainers.

Todo esto es trabajo futuro si/cuando el MVP madure hacia producto.

---

## 11. Open questions / decisiones diferidas al plan de implementación

1. **Validación del manifest — qué biblioteca.** Opciones: schema inline manual (stdlib), `jsonschema`, `pydantic`. Decisión al plan; para MVP se prefiere stdlib si basta.

2. **Smoke test en Fase 6 — `sleep(1)` vs. polling.** Poll GET hasta que la key aparezca (max 5s) es más robusto. Decisión al plan.

3. **Naming `v2` en el nombre del fichero.** Mantener durante la coexistencia con `env_client.py` legacy. Renombrar a `onboard_client.py` cuando el v1 se deprecie — tarea separada, no ahora.

4. **Manifest de otros clientes (ESAMUR, EDAR_MURCIA) para v2.** Cuando se migren, un `deploy/clients/<X>.yaml` adicional. No forma parte del MVP.

---

## 12. Historial

| Fecha | Autor | Cambio |
|---|---|---|
| 2026-04-17 | David Palazon / Claude | Primera versión — spec aprobado en brainstorming; entrada para writing-plans |
