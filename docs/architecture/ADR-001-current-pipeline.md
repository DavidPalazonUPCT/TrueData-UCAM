# ADR-001: Pipeline de telemetría actual (OPC → ThingsBoard → Node-RED)

- **Status:** Accepted (documentación retrospectiva del estado actual)
- **Date:** 2026-04-15
- **Autor:** David Palazon (UCAM), revisión Claude
- **Alcance:** Módulo `base` de TRUEDATA; pipeline de ingestión de telemetría industrial OPC-UA hacia ThingsBoard CE vía un cliente OPC externo y Node-RED como middleware ETL.

---

## 1. Contexto

UCAM integra datos de plantas de tratamiento de agua (ejemplo: Francisco /
FR_ARAGON) en ThingsBoard para dashboarding, alarmas y como fuente de
alimentación de modelos ML externos. Los datos llegan desde PLCs industriales
vía OPC-UA. Un cliente OPC custom (mantenido por Neoradix) consume los nodos
OPC, convierte a JSON y POSTea HTTP a ThingsBoard.

### 1.1 Características verificadas de los datos

Caso de referencia — FR_ARAGON (dump 30 días, 470 393 filas):

| Propiedad | Valor |
|---|---|
| Tags por scan | 27 (flujos, conductividades, pH, analógicos, digitales, heartbeat) |
| Cadencia nominal (Δt mediano) | **34,2 s** (σ = 0,35 s) |
| Jitter intra-scan | los 27 tags se escriben en el mismo ciclo PLC, separados por **milisegundos** (~0,001 s–0,003 s) |
| Uptime planta efectivo | 22,9 % (165,7 h activas vs 557 h de gaps; gap máximo 508 h) |
| Sincronismo entre tags | total (17 422 scans × 27 tags, sin desincronización) |
| Varianza útil | 18 de 27 tags (los 13 digitales `DI_00..DI_13` + `ERROR_COMM` son constantes) |

Consecuencia arquitectónica: **no es un stream continuo de alta frecuencia.**
Es un batch periódico (~34 s) de 27 valores casi simultáneos, con gaps
largos cuando la planta/router caen.

### 1.2 Restricciones originales (inferidas)

El pipeline se diseñó sin documentación de decisiones. Esta sección es
**inferencia a partir de evidencia en código**, sujeta a corrección cuando
se contacte con los autores originales:

- **TB CE < 4.0** no disponía de Calculated Fields. La agregación o
  derivación de series requería o rule chain + script custom o un ETL
  externo. Se eligió Node-RED por flexibilidad y bajo umbral de entrada.
- **OPC Client custom (Neoradix)** en vez de IoT Gateway oficial de TB:
  probablemente por preferencia del partner o por características del
  entorno industrial del cliente (conectividad OPC-DA legado, seguridad
  perimetral, licencias).
- **HTTP REST como transporte** en vez de MQTT: curva de aprendizaje más
  plana para Neoradix y trazabilidad más directa (curl-debuggeable).

### 1.3 Requisitos funcionales activos

- Ingesta OPC-UA → TB con semántica "at-least-once" al nivel de batch
- Almacenamiento de cada sensor como serie temporal en TB con `ts`
  derivado del PLC, no del wall-clock
- Vista agregada (media/mediana) en ventanas cortas para dashboards de
  operador (1 s / 5 s / 10 s — ver §3.3)
- Publicación de alarmas vía flujo "Critical Levels" (niveles de criticidad
  de variables de planta, con vigencia temporal)
- Provisionamiento reproducible por cliente vía pipeline Python (`deploy/`)
- Configuración por cliente (p.ej. ESAMUR, MCT, FR_ARAGON) vía `Client.json`
  + CSVs de dispositivos + plantillas JSON

---

## 2. Decisión

Se construye un pipeline HTTP-REST de 5 hops, con Node-RED como ETL entre
ThingsBoard y sí mismo. Diagrama:

```
                      ┌────────────────────────────┐
OPC-UA Server  ──────▶│  OPC Client (Neoradix)     │
(PLC planta)          │  - POST HTTP bulk: 27 tags │
                      │    por scan (~34 s)        │
                      └──────────────┬─────────────┘
                                     │ HTTP POST /api/v1/{rawToken}/telemetry
                                     ▼
                      ┌────────────────────────────┐
                      │  ThingsBoard: Raw Device   │
                      │  (1 device, 1 accessToken) │
                      │  - Save Timeseries raw     │
                      │  - Rule Chain: raw_root    │
                      └──────────────┬─────────────┘
                                     │ TbRestApiCallNode
                                     │ POST /endpoint/previoXXX
                                     ▼
                      ┌────────────────────────────┐
                      │  Node-RED: PrevioRawFlow   │
                      │  - Split bulk → N tags     │
                      │  - Lookup sensor→token     │
                      │    (global.diccionario)    │
                      │  - POST per-sensor         │
                      └──────────────┬─────────────┘
                                     │ HTTP POST /api/v1/{sensorToken}/telemetry
                                     ▼
                      ┌────────────────────────────┐
                      │  ThingsBoard: per-sensor   │
                      │  devices (N × profile_dev) │
                      │  - Save Timeseries         │
                      │  - Rule Chain: devices_root│
                      └──────────────┬─────────────┘
                                     │ TbRestApiCallNode
                                     │ POST /endpoint/agregarXXX
                                     ▼
                      ┌────────────────────────────┐
                      │  Node-RED: ETLflows        │
                      │  - Batch 1s/5s/10s         │
                      │  - Media, Mediana por      │
                      │    ventana                 │
                      └──────────────┬─────────────┘
                                     │ HTTP POST /api/v1/{bucketToken}/telemetry
                                     ▼
                      ┌────────────────────────────┐
                      │  ThingsBoard: bucket       │
                      │  devices (6: media 1/5/10, │
                      │  mediana 1/5/10)           │
                      │  - Save Timeseries         │
                      │  - Rule Chain: buckets_root│
                      └────────────────────────────┘

Ramas laterales: Critical Levels (alarmas) via NR flows separados.
Profiles ML (estimaciones, matriz, models) los alimenta otro partner.
```

### 2.1 Componentes y responsabilidades

| Componente | Rol | Justificación |
|---|---|---|
| **OPC Client (Neoradix)** | Puente OPC-UA → HTTP. Bulk POST de 27 tags por scan | Responsabilidad de partner; aislado por contrato HTTP |
| **Raw Device + `raw_root_rule_chain`** | Punto de entrada único; rule chain reenvía a NR para fan-out | Simplifica el contrato del OPC Client (un solo token, un solo endpoint) |
| **Node-RED `PrevioRawFlow`** | Fan-out del bulk a devices per-sensor | TB CE 3.x/4.x no tiene node rule-chain nativo para "split JSON → N POSTs dinámicos"; NR ofrece flexibilidad JS |
| **per-sensor devices + `devices_root_rule_chain`** | Almacenamiento granular. Cada sensor tiene token propio, rule chain común | Permite RBAC por sensor, queries TB API granulares, alarm rules per-device |
| **Node-RED `ETLflows`** | Batch + agregación en ventanas 1/5/10 s | Ver §3.3 |
| **bucket devices + `buckets_root_rule_chain`** | Almacenar series agregadas como devices separados | Permite dashboards TB sobre agregados sin queries computacionales por cada refresh |
| **Node-RED `Critical Levels` flows** | Recibir POSTs del admin panel, transformar, persistir niveles de criticidad en TB como atributos de device | Lógica condicional compleja con vigencia temporal mejor expresada en JS que en TBEL |

### 2.2 Transporte y seguridad

- **HTTP REST** sobre red interna Docker. Tokens en URL path
  (`/api/v1/{token}/telemetry`) — limitación de la API TB, no decisión de
  diseño (el endpoint TB acepta token solo en path).
- **Sin TLS interno**: toda la comunicación ocurre dentro de la red
  `truedata_iot_network` (Docker bridge). La terminación HTTPS es
  responsabilidad del reverse proxy externo cuando se expone TB/NR.
- **Autenticación admin**: TB tenant admin (`tenant@thingsboard.org` +
  password) y Node-RED admin (`tenant` + bcrypt hash) almacenadas en
  `deploy/ParametrosConfiguracion.txt` (deployment-side, no versionado).
- **Tokens de device**: generados por TB, cacheados en
  `deploy/<CLIENTE>/DeviceimportCredentials_<CLIENTE>.csv`
  (también deployment-side), y en runtime replicados en
  `global.diccionarioAccess` de Node-RED al arrancar.

### 2.3 Provisionamiento

`deploy/env_client.py` orquesta 5 scripts Python que crean en orden:
customer → rule chains (9) → device profiles (8) → devices base (N desde
`DeviceImport.csv`) → devices auxiliares (~54 por modelo × 3 modelos →
~160 devices por cliente) → flujos NR (vía API REST de Node-RED). Los
tokens resultantes se persisten en CSV local.

---

## 3. Decisiones específicas con tradeoff discutible

### 3.1 Bulk POST a Raw Device (vs POST per-sensor)

**Decisión:** el OPC Client envía un único POST con los 27 valores por scan,
dirigido a un device "Raw Data" único.

**Por qué:** contrato simple para Neoradix — un endpoint, un token, un
payload. No necesita conocer el inventario de devices TB ni sus tokens.

**Coste:** exige un paso de fan-out posterior (§3.2). TB no tiene API
REST nativa para "un POST, N devices" en CE 4.x salvo vía Gateway API
(MQTT-first).

**Alternativas no elegidas:**
- *OPC Client con tabla sensor→token*: más acoplamiento (Neoradix debería
  reconfigurar cada alta/baja de sensor).
- *TB Gateway API sobre MQTT*: más natural pero exigiría cliente MQTT en
  Neoradix; en su momento se priorizó HTTP.

### 3.2 Fan-out en Node-RED (vs en TB rule chain)

**Decisión:** el split del bulk payload en N POSTs per-device se hace en
Node-RED, no en un TBEL script de rule chain TB.

**Por qué:** NR ofrece JS libre, `http request` nodes, debugging visual.
TBEL en rule chain es más limitado y el debugging es menos ergonómico.

**Coste:** introduce un hop externo. Introduce estado en NR
(`global.diccionarioAccess`) sin invalidación explícita. Introduce
dependencia dura NR↔TB (si NR cae, el pipeline se corta aunque TB esté OK).

**Alternativas no elegidas:**
- *TBEL script node en `raw_root_rule_chain`*: eliminaría NR del path.
  Descartado por coste de reescritura y madurez de TBEL en TB CE en su
  momento.
- *TB Gateway API HTTP (si existiera)*: no hay confirmación documental de
  que CE soporte HTTP Gateway API equivalente al MQTT.

### 3.3 Ventanas de agregación 1s/5s/10s en Node-RED

**Decisión:** `ETLflows.json` calcula media y mediana sobre batches
temporales de 1, 5 y 10 s, publicándolos como devices independientes.

**Motivación original (inferida):** resolver el jitter intra-scan —
los 27 tags con timestamps separados por ms se colapsan en eventos
temporalmente alineados. Adicionalmente, dashboards de operador querían
tasas "redondas" en segundos.

**Realidad con el cadence observado (§1.1):**

> **La cadencia nativa del PLC es ~34 s. Una ventana de 1 s contiene 0 o 1
> sample. Una mediana de 1 sample es ese sample; una mediana de 0 samples
> es un no-op. La agregación estadística aporta poco — lo que aporta valor
> real es el _alineamiento temporal_ (truncar timestamps al segundo o al
> scan) y el _dedupe de jitter_.**

**Bugs derivados que la implementación actual tiene:**
- `accumulate: true` en los nodos batch sin reset explícito → crecimiento
  indefinido de memoria en Node-RED hasta OOM o restart
- Ventanas *wall-clock*: si un paquete llega con `ts` histórico (p.ej.
  store-and-forward tras un gap), cae en la ventana del reloj actual, no
  en la del `ts` real
- Comentario explícito en código: `EL PROCESO ACTUAL PIERDE EL PRIMER
  REGISTRO` (ver `PrevioRawFlow.json:484`) — un split por newline
  descarta el primer item en ciertas condiciones

**Alternativas modernas disponibles hoy:**
- *TB Calculated Fields* (CE 4.0+): `median`, `mean`, `std` nativos sobre
  rolling windows declarativas. Cubre el caso con cero scripting. No se
  adoptó porque CF no existía cuando se construyó el pipeline.

**Mitigación actual:** ninguna documentada; los bugs conviven con el
sistema. Ver §5 para plan.

### 3.4 Critical Levels en Node-RED (vs TB Alarm Rules)

**Decisión:** los niveles de criticidad (cotas con fecha inicio/fin)
se gestionan via flujos NR con endpoint `/endpoint/NivelesCriticidad*`.

**Por qué (inferido):** TB Alarm Rules en su momento eran más limitadas
para el modelo de "cota con vigencia temporal + lookup cross-device".

**Coste:** 3 flujos NR (`flows Critical Levels.json`, `...Levels2.json`,
`...Levels old.json`), el último claramente deprecated (A/B abortado).

### 3.5 Fichero `ParametrosConfiguracion.txt` para credenciales

**Decisión:** los scripts `deploy/` leen credenciales TB y NR de un
fichero JSON local en `deploy/<CLIENTE>/ParametrosConfiguracion.txt`.

**Por qué:** en dev los secretos vivían en fichero local, simple de
editar. Más tarde se portó como-es.

**Coste:** requiere fichero por cliente local en el runner; no se
integra con secret managers estándar (Vault, GitLab CI secrets).

**Mitigación (post-MR-2 GitLab):** `PARAMETROS_PATH` env var hace el path
flexible. TODO abierto: refactor a env vars puras (`TB_ADMIN_USER`,
`TB_ADMIN_PASSWORD`, etc.) documentado en `base/deploy/README.md §10`.

---

## 4. Consecuencias

### 4.1 Positivas

- **Desacoplamiento del OPC Client**: Neoradix solo necesita saber un
  endpoint y un token. Cualquier cambio arquitectónico interno es
  transparente para ellos.
- **Visibilidad**: Node-RED aporta debugging visual del flujo, útil en
  setup inicial y troubleshooting.
- **Flexibilidad JS**: transformaciones custom, lookups, lógica
  condicional se añaden fácil sin esperar a features de TB.
- **Provisionamiento reproducible**: `env_client.py` garantiza que
  cualquier cliente se puede levantar desde cero en minutos (asumiendo
  stack TB+NR levantado).

### 4.2 Negativas (aceptadas con mitigación planificada)

- **5 hops HTTP**: irrelevante en throughput (cadencia 34 s), pero añade
  puntos de fallo. Mitigación: monitoring + healthchecks (añadidos en
  MR-1 del aporte GitLab).
- **Estado en NR sin TTL**: `global.diccionarioAccess` no se invalida;
  rotación de tokens TB exige restart de NR. Mitigación pendiente:
  añadir refresh periódico o invalidación al recibir 401.
- **Ventanas inútiles con cadencia 34 s**: §3.3. Riesgo: OOM en NR por
  acumulador. Mitigación inmediata: fijar `accumulate: false` o resetear
  ventanas (ver MR de bugfixes).
- **Tokens en URL path**: limitación de la API TB, no decisión UCAM.
  Mitigación: usar `Authorization: Bearer <token>` donde TB lo acepte
  (admin API sí; device telemetry API no — aquí estamos atados).
- **Acoplamiento NR↔TB**: caída de NR rompe el pipeline completo.
  Mitigación pendiente: store-and-forward en OPC Client + rule chain
  TB que persista raw aunque NR esté abajo.
- **Deploy pipeline manual**: `env_client.py` se lanza a mano. Mitigación
  pendiente: integrar en CI con secrets management.

### 4.3 Explícitamente no garantizadas

Este pipeline **no** garantiza:
- Exactly-once (puede haber duplicados si OPC Client reintenta sin dedupe)
- Orden estricto entre tags del mismo scan (el jitter intra-ms se
  preserva hasta el ETL, que lo colapsa)
- Recuperación ante pérdida de NR (los datos en el device Raw se
  almacenan, pero el fan-out y agregación no se reprocesan)

Cualquiera de estas propiedades requeriría rediseño explícito.

---

## 5. Plan de mitigación (backlog, no-compromiso)

Priorizado por ROI — ítems marcados `[MR-Xxx]` tienen branch/MR asociado
en GitLab o UCAM.

**Alta prioridad (bugfixes aceptados):**

- `[MR-base-bugfixes]` Fijar `accumulate: false` en batch nodes `ETLflows`
- `[MR-base-bugfixes]` Investigar y fix del "pierde primer registro"
- `[MR-base-bugfixes]` URL hardcoded `portal.airtrace.io:1880` en
  `mct_raw_root_rule_chain.json` → variable interpolada
- `[MR-base-bugfixes]` Mover admin tokens (NR/TB) de URL a
  `Authorization` header donde la API lo permite

**Media prioridad (operacional, defensivo INCIBE):**

- Observability stack: Prometheus exporter de TB + dashboard Grafana
  "lifeline" (telemetría/s, latencia rule chain, errores NR)
- Runbooks: caída TB, caída NR, rotar TB admin, rotar NR
  `credentialSecret` (no-rotable, requiere plan B)
- Test E2E mínimo: simulator → TB → NR → bucket, en CI
- Rate limits TB activados (desactivados por defecto en CE)
- mTLS opcional entre TB y NR (CE lo soporta)

**Baja prioridad / futuro (arquitectura v2, condicional):**

> Este bloque **NO debe ejecutarse** sin uno de estos triggers:
> (a) evidencia en producción de fallo recurrente; (b) checklist INCIBE
> explícito que lo pida; (c) Neoradix bloqueado por el contrato HTTP
> actual.

- Sustituir `ETLflows` por Calculated Fields (si vienen métricas
  estadísticas reales; hoy no aportan con cadencia 34 s → candidato a
  eliminar sin reemplazo)
- Sustituir fan-out en NR por TBEL script en `raw_root_rule_chain`
- Eliminar `profile_buckets` + sub-devices si se elimina ETLflows
- Migrar Critical Levels NR flows a TB Alarm Rules nativas

---

## 6. Alternativas arquitectónicas evaluadas y descartadas

| Alternativa | Por qué descartada |
|---|---|
| **MQTT como transporte principal** | Neoradix ya tiene cliente OPC HTTP en dev. Cambio de transporte implica reescribir su componente, coste sin evidencia de beneficio |
| **TB IoT Gateway oficial para OPC-UA** | Convierte el entregable de Neoradix de "contenedor con código" a "fichero de configuración". Rechazado por UCAM: scope change a mitad de desarrollo |
| **Kafka/Pulsar como bus intermedio** | Overkill para cadencia 34 s. Aporta exactly-once, backpressure, replay pero con coste operacional desproporcionado para el throughput real |
| **Eliminar Node-RED del path crítico** | Factible (ver §3.2 y §3.3 alternativas), pero requiere rediseño sin driver de negocio actual. Ver §5 plan de mitigación bloque "arquitectura v2" |
| **Refactor v2 hoy (pre-producción)** | Sin evidencia de fallo, sin checklist INCIBE, sin feedback de operador, el refactor especulativo destruye baseline de comparación y consume presupuesto sin ROI demostrable |

---

## 7. Referencias

- CONTRIBUTING.md del repo GitLab TRUEDATA — gobernanza de MRs
- Plan de contribución UCAM: `docs/superpowers/plans/2026-04-14-truedata-gitlab-base-contribution.md`
- Reverse-engineering del pipeline (auditoría interna, sesión 2026-04-15):
  identificó bugs §4.2 y permitió el presente ADR
- Datos caracterizados (FR_ARAGON): 17 422 scans × 27 tags, 30 días,
  procesados desde dump PostgreSQL (`connect_opcua_itemvalue`)
- ThingsBoard CE 4.x docs:
  - [Gateway MQTT API](https://thingsboard.io/docs/reference/gateway-mqtt-api/)
  - [Calculated Fields](https://thingsboard.io/docs/user-guide/calculated-fields/)
  - [Rule Engine Queues](https://thingsboard.io/docs/user-guide/rule-engine-2-5/queues/)

---

## 8. Historial del documento

| Fecha | Autor | Cambio |
|---|---|---|
| 2026-04-15 | David Palazon / Claude | Primera versión — captura del estado actual pre-contribución GitLab |
