# ADR-002: Ventanas de agregación y store-and-forward — decisiones abiertas pre-producción

- **Status:** Proposed (preguntas abiertas; requiere input de partners externos)
- **Date:** 2026-04-15
- **Autor:** David Palazon (UCAM), revisión Claude
- **Contexto previo:** [ADR-001](ADR-001-current-pipeline.md) documenta la arquitectura actual y sus tradeoffs. Este ADR cubre dos decisiones específicas que afloraron al analizar el dataset del *early adopter* FR_ARAGON y que requieren información de terceros (equipo ML, Neoradix) antes de cerrarse.

---

## 1. Contexto

FR_ARAGON es el primer cliente en pasar a producción con el módulo base de TRUEDATA. El análisis del dump PostgreSQL de su app Django+OPC-UA (30,1 días, 470 393 filas sobre `connect_opcua_itemvalue`) arrojó dos hechos que colisionan con supuestos del pipeline:

### 1.1 Cadencia real

- **Δt mediano entre scans: 34,2 s** (σ = 0,35 s), confirmado sobre `Q_SALIDA_D1`
- Los 27 tags del PLC se escriben en el mismo ciclo, separados por jitter intra-scan de milisegundos
- **Uptime efectivo 22,9 %** (165,7 h activas vs 557 h de gaps; gap máximo 508 h, ~21 días)

### 1.2 Contrato con el modelo ML

El modelo consumidor downstream fue diseñado con **la premisa "la agregación es necesaria"** y lee de los 6 devices buckets que produce `ETLflows`:

- `Aggregation Media Ventana 1 seg`, `5 seg`, `10 seg`
- `Aggregation Mediana Ventana 1 seg`, `5 seg`, `10 seg`

Esos devices y sus nombres forman el contrato de entrada del modelo.

---

## 2. Las dos preguntas abiertas

### 2.1 ¿Las ventanas 1s/5s/10s siguen teniendo sentido con cadencia 34 s?

**Hecho objetivo:** con cadencia 34 s, cada ventana contiene 0 o 1 sample por sensor (probabilístico). Una mediana de 0 samples es un no-op; una mediana de 1 sample es el propio sample. Las funciones `media` y `mediana` tal y como están configuradas degeneran en **aproximadamente la identidad** del valor raw, más ruido estadístico (ventana vacía vs no vacía en función del reloj).

**Implicación:** los 6 devices buckets producen, para FR_ARAGON, series funcionalmente indistinguibles del raw per-device. El pipeline gasta hops para producir información redundante.

**Pregunta que no se puede contestar sin el equipo ML:**

> ¿El modelo se entrenó con datos a 34 s (mismo régimen que FR_ARAGON, y por tanto aprendió a operar sobre aggregates degenerados) o a cadencia más alta (p.ej. 1 Hz, donde la agregación sí añadía info)?

- **Caso A — modelo entrenado a 34 s:** el contrato es consistente con el régimen de producción. El modelo "espera" aggregates cuasi-identidad y los usa. No hay problema funcional; hay problema de eficiencia (cálculo redundante) que se puede diferir.
- **Caso B — modelo entrenado a cadencia mayor:** FR_ARAGON opera fuera del régimen de entrenamiento. Los aggregates que recibe el modelo no tienen la distribución de los del entrenamiento. **El modelo puede dar resultados inválidos y nadie lo sabe.** Esta hipótesis es la que debería preocupar más.

### 2.2 ¿El cliente OPC de Neoradix tiene store-and-forward suficiente para gaps de 21 días?

**Hecho objetivo:** FR_ARAGON tuvo un gap de 508 h en el dataset (probablemente Navidad o router caído). Durante ese periodo, o bien el PLC seguía escribiendo localmente (y el cliente OPC lo recuperó al volver), o bien los datos se perdieron.

**Implicación:** el cliente OPC actual (HTTP, en dev) debe poder absorber:
- Caídas de TB de **minutos/horas** sin perder datos (caso común)
- Gaps de **días/semanas** por parte de la planta (caso extremo observado)

**Pregunta que no se puede contestar sin Neoradix:**

> ¿Qué hace el cliente OPC cuando `POST` a TB falla? ¿Retry con backoff + cola persistente en disco? ¿Memoria volátil (se pierde al reiniciar)? ¿Drop directo?

Esto es el punto más crítico para producción INCIBE-ready. Mucho más importante que el tema ventanas. Sin persistencia en disco, cualquier gap de comunicación = pérdida permanente de datos.

---

## 3. Decisiones tomadas ahora (sin esperar a las respuestas)

### 3.1 Preservar el contrato de las 6 ventanas

- **No** se cambian device names
- **No** se cambian intervalos 1s/5s/10s
- **No** se añaden devices shadow con ventanas mayores (hasta que el equipo ML lo valide)

Razón: rompería al modelo consumidor y no tenemos input suficiente del equipo ML para rediseñar.

### 3.2 Estabilizar la agregación (hemorragia ya parada)

- `accumulate: true` → `false` en los 3 join nodes de `ETLflows.json` (fix aplicado en MR `feature/base/pipeline-legacy-bugfixes`, commit `12ca3a0`)
- Eliminado el memory leak que crecía scan a scan en Node-RED

### 3.3 Diferidos conscientemente

- **Snap de `ts` al segundo** en el ingesta (dedup intra-scan): útil pero no crítico mientras no se hable con ML team. Si Caso A (modelo entrenado a 34 s ya vio esos datos sin dedup), cambiar la semántica ahora podría degradar el modelo. Diferido a la validación ML.
- **Skip de ventanas vacías**: mismo razonamiento. Si el modelo aprendió a usar slots vacíos como señal de "planta parada", rellenarlos rompe.
- **Redimensionar ventanas a 15 min / 1 h / 1 día**: requiere rehacer modelo.

### 3.4 Hallazgos del análisis marcados como informativos

- **13 digitales con varianza cero (`DI_00..DI_13`, `ERROR_COMM`):** no filtrar en ingesta. Mejor: añadir alarma TB por cambio en cualquiera de ellos. Un DI que deja de ser constante es un evento de interés (fallo hardware probable).
- **`EA_2/3/4` valores negativos (−2700):** problema de escalado 4-20mA en el PLC, no en el pipeline. Documentar en runbook: "si EA_* negativo, revisar calibración PLC, no pipeline".

---

## 4. Riesgos y priorización

| # | Riesgo | Probabilidad | Impacto | Si ocurre en producción |
|---|---|---|---|---|
| R1 | Modelo ML fue entrenado con cadencia ≠ 34 s → predicciones inválidas en FR_ARAGON | Media | Alto | Decisiones operativas incorrectas basadas en scoring del modelo. Requiere retraining o downgrade del modelo |
| R2 | Cliente OPC de Neoradix sin store-and-forward persistente → pérdida de datos en cualquier caída | **Alta** (hasta que se confirme lo contrario) | **Alto** | Gaps silenciosos en series de sensores. Indetectable sin monitoring específico |
| R3 | Operadores no saben que aggregates 1s/5s/10s son degenerados → toman decisiones sobre métricas que no añaden información | Baja (si no se construyen dashboards sobre esos devices) | Bajo | Confusión interna; no afecta planta |
| R4 | Las 13 digitales constantes son símbolo de problema hardware silencioso | Baja | Medio | Perdemos visibilidad de eventos. Mitigación propuesta: alarma por cambio |
| R5 | Re-entrenamiento del modelo con features útiles (ventanas reales) requiere coordinación multi-partner y tiempo | — | — | No bloquea producción si se preserva el contrato actual |

**Priorización:** R2 >> R1 > R4 > R3. R2 es el único que puede causar pérdida de datos silenciosa; los demás son problemas de calidad de señal o de decisiones informadas.

---

## 5. Acciones siguientes (responsables)

### UCAM
- [ ] Preguntar al equipo ML: cadencia del dataset de entrenamiento, régimen de features esperado, sensibilidad del modelo a cambios de cadencia
- [ ] Escribir runbook: "EA_* negativo → revisar PLC", "DI cambia → investigar planta" (`docs/runbooks/`)
- [ ] Cuando haya luz del equipo ML, decidir si:
  - Caso A → nada que hacer, el pipeline está bien
  - Caso B → plan de re-entrenamiento con ventanas reales (15 min / 1 h / 1 día) + shadow pipeline temporal

### Neoradix
- [ ] Responder: ¿cliente OPC tiene store-and-forward en disco? ¿Qué mecanismo? ¿TTL de la cola local?
- [ ] Si la respuesta es "no" o "solo memoria":
  - Añadir SQLite local queue (patrón estándar: `paho-mqtt` style)
  - Reintentos con backoff exponencial
  - Métrica de backlog (cuántos mensajes encolados localmente)
- [ ] Documentar en `base/opc-client/README.md` §9 (Testing) una prueba de caída de TB para verificar la cola

### Ambos / Coordinación
- [ ] Checkpoint cuando ambas preguntas estén respondidas: revisar este ADR, cerrarlo o actualizarlo a Accepted/Superseded

---

## 6. Cuándo reabrir este ADR

Este ADR se marca **Proposed** hasta que una de estas tres condiciones se cumpla:

1. Equipo ML confirma Caso A + Neoradix confirma store-and-forward persistente → ADR pasa a **Accepted** con subtítulo "pipeline actual es adecuado para FR_ARAGON"
2. Equipo ML confirma Caso B → nuevo ADR-003 con plan de migración de features
3. Neoradix no puede entregar store-and-forward → escalar, posible bloqueante para ir a producción

---

## 7. Referencias

- [ADR-001](ADR-001-current-pipeline.md) — arquitectura actual del pipeline (decisiones pasadas)
- Plan de contribución UCAM GitLab: `docs/superpowers/plans/2026-04-14-truedata-gitlab-base-contribution.md` Apéndice F (MR landings)
- MR de bugfixes en GitLab: `feature/base/pipeline-legacy-bugfixes` (commit `12ca3a0`)
- Dataset FR_ARAGON: `C:\Users\david\TrueData\FlowGuard\data\raw\FR_ARAGON\Francisco_16_01_2026.sql`

---

## 8. Historial del documento

| Fecha | Autor | Cambio |
|---|---|---|
| 2026-04-15 | David Palazon / Claude | Primera versión — captura de preguntas abiertas post-análisis FR_ARAGON |
