# TrueData System Sizing Calculator (INCIBE)

Visualización interactiva del dataset empírico de benchmarking del sistema de detección
de anomalías GNN de TrueData sobre dispositivos edge representativos. La aplicación
muestra los valores medidos directamente en el grid común de nodos
**N ∈ {20, 50, 100, 200, 500}** y produce veredictos de viabilidad sobre esos puntos
para cada combinación dispositivo–modelo.

---

## Demo rápida

### Opción A: Dev server (recomendada para desarrollo)

```bash
cd system_sizing
npm install
npm run dev -- --host 0.0.0.0   # --host necesario en WSL2
```

Abre `http://localhost:5175`. No necesita Python ni servicios externos.

### Opción B: Build estático

```bash
cd system_sizing
npm run build
npm run preview
```

> El build de producción usa `base: "/TrueData/system-sizing/"`. Para previsualizarlo
> localmente usa `npm run preview`, que resuelve el base path correctamente.

---

## Métricas que visualiza

La SPA cubre las dos fases obligatorias del profiler (cold start y warm latency) y
todas las métricas que producen los barridos multidimensionales sobre el grid común:

- Latencia P50, P95 y P99 por configuración.
- Cold start desglosado en sus tres componentes (instanciación del modelo, carga de
  artefactos, primera inferencia).
- RSS peak y baseline por configuración, con desglose en checkpoints.
- Desglose porcentual por fases del pipeline (preprocesamiento, forward, cómputo de
  error, scoring).
- Throughput de entrenamiento y tiempo total proyectado analíticamente (dataset /
  throughput × épocas).
- Veredicto de viabilidad (Excellent / Viable / Tight / Not viable) para cada
  combinación dispositivo–modelo, calculado sobre los mismos umbrales que el documento
  metodológico.

---

## Dispositivos y modelos

Seis perfiles de evaluación cubriendo las cuatro categorías edge descritas en la
metodología (SBC ARM, mini PC x86, embebido ARM con GPU integrada y portátil x86 con GPU
discreta):

| Perfil | Device | RAM | Arch | GPU / CUDA | Fichero |
|---|---|---|---|---|---|
| SBC ARM | Raspberry Pi 5 | 16 GB | ARM64 | — | `rpi5.json` |
| mini PC x86 | Beelink EQ14 (Intel N150) | 16 GB | x86_64 | — | `beelink.json` |
| Embebido ARM (CPU) | Jetson Orin Nano | 8 GB (unificada) | ARM64 | Ampere 1024 CUDA (no activa) | `j30-cpu.json` |
| Embebido ARM (CUDA) | Jetson Orin Nano | 8 GB (unificada) | ARM64 | Ampere 1024 CUDA / 12.6 | `j30-cuda.json` |
| Portátil x86 (CPU) | MSI i7-13700H | 16 GB | x86_64 | RTX 4060 (no activa) | `pc-dev.json` |
| Portátil x86 (CUDA) | MSI i7-13700H | 16 GB | x86_64 | RTX 4060 / 12.8 | `pc-dev-cuda.json` |

Arquitecturas GNN evaluadas (idénticas en todos los dispositivos):

| Modelo | Descripción |
|---|---|
| CoGNN | Co-evolutional GNN, referencia principal del proyecto |
| STGNN-GAT | Spatio-Temporal GNN con Graph Attention |
| STGNN-TopK | Spatio-Temporal GNN con TopK pooling |

## Volumen de la campaña publicada

| Régimen | Configuraciones por perfil | Perfiles | Mediciones totales |
|---|---|---|---|
| Inferencia | 15 (3 modelos × 5 nodos, ventana y batch fijos) | 6 | 90 |
| Entrenamiento | 375 (3 modelos × 5 batch × 5 nodos × 5 volúmenes) | 6 | 2 250 |
| **Total** |  |  | **2 340** |

Las fechas exactas de ejecución, versiones de PyTorch y Python y el schema de reporte
por dispositivo se incluyen en el campo `meta` de cada JSON de `public/data/`.

---

## Tabs de la SPA

| Tab | Contenido |
|---|---|
| **Overview** | Recomendación automática + tabla comparativa dispositivo × modelo + scatter Pareto (latencia P95 vs RAM combinada) |
| **Inferencia** | Por dispositivo: tabla resumen + gráfico de latencia empírica por N + métricas por modelo + desglose por fases |
| **Training** | Por dispositivo: throughput, tiempo por época y total, RAM incremental para dataset y épocas configurados |
| **Hardware** | Tabla de especificaciones (CPU, RAM, GPU, CUDA, overhead del stack, fecha del benchmark) |
| **Metodología** | Resumen en pantalla alineado con el docx: por qué medir empíricamente, entorno de pruebas, métodos de inferencia y entrenamiento, criterios de viabilidad |

---

## Criterios de viabilidad (acordes con el docx)

**Inferencia** — dos dimensiones simultáneas:

| Veredicto | Budget ratio (P95 latencia / ventana ETL) | Memory ratio (RSS peak / RAM disp.) |
|---|---|---|
| Excellent | ≤ 0,25 | ≤ 0,80 |
| Viable | ≤ 0,50 | ≤ 0,80 |
| Tight | ≤ 0,80 | ≤ 0,90 |
| Not viable | > 0,80 | > 0,90 |

**Entrenamiento** — una dimensión (el proceso batch puede reintentarse con parámetros
reducidos):

| Veredicto | RSS estimado / RAM disponible |
|---|---|
| Viable | ≤ 0,80 |
| Tight | ≤ 0,95 |
| Not viable | > 0,95 |

**RAM disponible** = `RAM_total − stack_overhead`. El `stack_overhead_mb` se mide
empíricamente en cada dispositivo con el stack completo de producción activo.

---

## Datos

Los JSON de dispositivo en `public/data/` provienen del pipeline de benchmarking
descrito en la metodología (barridos de inferencia y entrenamiento), recortados al grid
común de nodos. Solo contienen los campos consumidos por la SPA: cada entrada de
inferencia y entrenamiento incluye latencia, memoria y desglose por fases del pipeline.

Estructura simplificada de cada device JSON:

```json
{
  "meta": {
    "device_id": "rpi5",
    "device_name": "Raspberry Pi 5",
    "arch": "arm64",
    "ram_total_gb": 15.8,
    "stack_overhead_mb": 4093.6,
    "measured_node_counts": [20, 50, 100, 200, 500],
    "measured_num_samples": [425, 850, 1700, 4250, 8500],
    "benchmark_date": "2026-03-30",
    "software": { "pytorch_version": "2.10.0+cpu", "python_version": "3.12.13" }
  },
  "inference": [
    {
      "model": "cognn", "num_nodes": 20,
      "latency": { "p50_ms": 128, "p95_ms": 232, "p99_ms": 339, "mean_ms": 148, "std_ms": 47 },
      "cold_start": { "total_ms": 2658 },
      "memory": { "rss_peak_mb": 471, "rss_baseline_mb": 285 },
      "phases": { "preprocess_pct": 0.1, "forward_pct": 99.6 },
      "datapoints_per_sec": 135.1
    }
  ],
  "training": [
    {
      "model": "cognn", "num_nodes": 20, "batch_size": 16, "num_samples": 425,
      "throughput_samples_per_sec": 18.55,
      "memory": { "rss_peak_mb": 480, "rss_baseline_mb": 408 },
      "recommended_batch_size": true
    }
  ]
}
```

El schema completo (incluyendo todos los checkpoints de memoria y métricas secundarias
usados por la SPA) está definido con Zod en `src/lib/schema.ts` y tipado en
`src/lib/types.ts`.

---

## Estructura del código

```
system_sizing/
├── index.html
├── package.json
├── vite.config.ts                # puerto 5175, base "/TrueData/system-sizing/"
├── tsconfig.json                 # strict, noUncheckedIndexedAccess
├── public/data/                  # 6 device JSONs (filtrados a N={20,50,100,200,500})
└── src/
    ├── App.tsx                   # Layout + 5 tabs
    ├── lib/
    │   ├── types.ts              # DeviceData, ModelId, Verdict, …
    │   ├── schema.ts             # Validación Zod
    │   ├── calculations.ts       # Verdicts, aceleración, tiempo training
    │   ├── i18n.ts               # ES + EN
    │   └── url-state.ts          # Persistencia query-string
    ├── hooks/
    │   ├── useDeviceData.ts      # Carga los 6 JSON
    │   └── useSizingCalc.ts      # Estado central + resultados calculados
    └── components/
        ├── layout/               # TopBar, Sidebar
        ├── tabs/                 # OverviewTab, InferenceTab, TrainingTab,
        │                         # HardwareTab, MethodologyTab
        ├── charts/               # LatencyBarChart, LatencyCurveChart (empírico),
        │                         # ParetoChart, MemoryBar, PhaseBreakdown, ThroughputChart
        ├── controls/             # DeviceSelector, DiscreteSlider, NumericInput
        └── ui/                   # MetricCard, VerdictBadge, DataBadge, Tip, Latex
```

### Dónde tocar para modificar

| Cambio | Fichero(s) |
|---|---|
| Añadir dispositivo | `src/hooks/useDeviceData.ts` (array `DEVICE_FILES`) + JSON en `public/data/` |
| Ajustar umbrales de veredicto | `src/lib/calculations.ts` (`inferenceVerdict`, `trainingVerdict`) |
| Cambiar valores por defecto del sidebar | `src/lib/url-state.ts` (`DEFAULTS`) |
| Texto de la metodología | `src/components/tabs/MethodologyTab.tsx` |
| Idioma / traducciones | `src/lib/i18n.ts` |

---

## Stack técnico

React 18 · TypeScript 5.5 · Vite 6 · Tailwind 4 · Recharts 2 · Zod 3 · KaTeX · Vitest 2.

## Build para producción

```bash
npm run build    # → dist/ con base "/TrueData/system-sizing/"
```

## Tests

```bash
npm test         # 17 tests (validación Zod + cálculos)
npm run test:watch
```

---

## Troubleshooting

| Problema | Causa | Solución |
|---|---|---|
| `npm run dev` da página en blanco | JSON no valida el schema Zod | Revisa la consola del navegador. Verifica que el JSON cumple el schema de `src/lib/schema.ts` |
| `npm run build` falla en `tsc` | Error de tipos | `npx tsc -b` muestra el error |
| El build dice 404 en los JSON | Base path incorrecto | En dev usa `npm run dev`. En build estático usa `npm run preview` |
| `localhost` no accesible desde Windows | WSL2 aísla localhost | Usa `npm run dev -- --host 0.0.0.0` y abre la URL "Network" que imprime Vite |
| No aparece N=150 en el slider | Solo puntos medidos | Por diseño la SPA sólo muestra los cinco puntos del grid común N ∈ {20, 50, 100, 200, 500} |

