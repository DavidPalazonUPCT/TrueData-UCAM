import {
  BookOpen, Activity, BarChart3, Brain,
  Shield, ChevronRight,
} from "lucide-react";

function Section({ icon: Icon, title, children }: { icon: typeof BookOpen; title: string; children: React.ReactNode }) {
  return (
    <section className="bg-surface border border-border rounded-lg overflow-hidden">
      <div className="px-5 py-4 border-b border-border flex items-center gap-2.5">
        <Icon size={16} className="text-primary shrink-0" />
        <h3 className="text-sm font-bold text-text">{title}</h3>
      </div>
      <div className="p-5 space-y-4">{children}</div>
    </section>
  );
}

function SubSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-text uppercase tracking-wider">{title}</h4>
      {children}
    </div>
  );
}

function Para({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-text-secondary leading-relaxed">{children}</p>;
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex gap-2 text-xs text-text-secondary leading-relaxed">
      <ChevronRight size={12} className="text-primary shrink-0 mt-0.5" />
      <span>{children}</span>
    </li>
  );
}

export function MethodologyTab() {
  return (
    <div className="space-y-5 max-w-4xl">
      {/* Header */}
      <div className="bg-surface border border-border rounded-lg px-5 py-4">
        <h2 className="text-base font-bold text-text">Metodología de Benchmarking</h2>
        <p className="text-xs text-text-muted mt-1">
          Proyecto TrueData — Detección de Anomalías en Infraestructuras Hídricas ICS/SCADA. Financiado por
          INCIBE (Programa de Investigación en Ciberseguridad).
        </p>
      </div>

      {/* 1. Motivation */}
      <Section icon={BookOpen} title="1. Por qué medir empíricamente">
        <Para>
          El sistema TrueData se despliega directamente en dispositivos edge situados en plantas de tratamiento
          de agua. Esta decisión responde a tres requisitos del contexto de infraestructura crítica:
          aislamiento de red, reducción de la superficie de ataque y latencia de detección. El dispositivo edge
          debe ejecutar el stack completo: plataforma IoT, base de datos, ETL, API y servicio de detección de
          anomalías basado en GNN.
        </Para>
        <SubSection title="Limitaciones del cálculo teórico">
          <ul className="space-y-1.5">
            <Bullet>
              <strong>Memoria no determinable analíticamente</strong>: el runtime de PyTorch reserva memoria
              para tensores intermedios del autograd, estados del optimizador (Adam triplica los parámetros) y
              cachés del allocator que no se pueden estimar a priori.
            </Bullet>
            <Bullet>
              <strong>Dependencia ISA</strong>: las operaciones <em>sparse</em> (scatter/gather/index_select)
              características de los GNN interactúan de forma distinta con la jerarquía de caché y las
              instrucciones SIMD de cada arquitectura (AVX-512 vs NEON).
            </Bullet>
            <Bullet>
              <strong>Escalado no lineal</strong>: en un grafo de N nodos el número de aristas crece como
              N×(N-1). Las optimizaciones del runtime y los efectos de caché introducen discontinuidades en la
              curva real que sólo se revelan midiendo.
            </Bullet>
          </ul>
        </SubSection>
      </Section>

      {/* 2. Test environment */}
      <Section icon={Activity} title="2. Entorno de pruebas">
        <SubSection title="Containerización y stack de producción completo">
          <Para>
            Todas las mediciones se ejecutan dentro del contenedor del stack TrueData con el resto de servicios
            de producción activos simultáneamente. En un dispositivo de 8 GB de RAM el stack puede consumir
            3-5 GB antes de que el servicio de ML comience a operar; medir en un dispositivo vacío reflejaría
            una disponibilidad de memoria que no existe en operación real. El campo{" "}
            <code className="text-primary font-mono text-[10px]">stack_overhead_mb</code> se mide
            empíricamente para cada dispositivo.
          </Para>
        </SubSection>

        <SubSection title="Reproducibilidad determinista">
          <Para>
            Cada ejecución fija las semillas de todos los generadores aleatorios (Python, NumPy, PyTorch CPU y
            CUDA) en{" "}
            <code className="text-primary font-mono text-[10px]">seed = 42</code>. Se activan las operaciones
            deterministas de PyTorch y se desactiva{" "}
            <code className="text-primary font-mono text-[10px]">cudnn.benchmark</code>. El profiler captura un
            snapshot completo del entorno (governor del CPU, número de hilos, temperaturas, frecuencias) al
            inicio y al final de cada ejecución.
          </Para>
        </SubSection>

        <SubSection title="Aislamiento del garbage collector">
          <Para>
            Durante la fase de medición de latencia el GC de Python se desactiva (
            <code className="text-primary font-mono text-[10px]">gc.disable()</code>) y se reactiva
            inmediatamente después. Una recolección de basura podría interrumpir una iteración varios
            milisegundos, generando outliers espurios en P95/P99.
          </Para>
        </SubSection>

        <SubSection title="Limpieza entre configuraciones (sweeps)">
          <Para>
            En barridos multi-configuración se ejecutan tres ciclos de{" "}
            <code className="text-primary font-mono text-[10px]">gc.collect()</code> entre configuraciones
            para minimizar la deriva de baseline de memoria. En CUDA se invocan adicionalmente{" "}
            <code className="text-primary font-mono text-[10px]">torch.cuda.empty_cache()</code> y{" "}
            <code className="text-primary font-mono text-[10px]">torch.cuda.reset_peak_memory_stats()</code>.
            Sin esta limpieza, la memoria residual de una configuración inflaría las mediciones de la
            siguiente.
          </Para>
        </SubSection>
      </Section>

      {/* 3. Inference methodology */}
      <Section icon={BarChart3} title="3. Metodología — Inferencia">
        <SubSection title="Configuración del sweep">
          <Para>
            100 iteraciones de medición tras 25 de warmup, batch size = 1, longitud de secuencia
            <code className="text-primary font-mono text-[10px] mx-1">seq_in_len = 12</code>. Se evalúan las
            tres arquitecturas GNN (CoGNN, STGNN-GAT, STGNN-TopK) sobre el subconjunto común de nodos:
            <strong> N ∈ {"{20, 50, 100, 200, 500}"}</strong>.
          </Para>
        </SubSection>

        <SubSection title="Métricas registradas">
          <ul className="space-y-1.5">
            <Bullet>
              <strong>Latencia P50/P95/P99</strong>: percentiles de la distribución de latencia por iteración.
              P95 es la métrica primaria de sizing — conservadora para SLA sin estar dominada por el ruido de
              cola del P99.
            </Bullet>
            <Bullet>
              <strong>Cold start</strong>: tiempos de arranque desglosados (model_init, artifact_init,
              first_inference).
            </Bullet>
            <Bullet>
              <strong>Memoria RSS</strong>: baseline, post-init y peak. Contabilidad segregada permite
              responder "¿es el modelo o los datos lo que no cabe?".
            </Bullet>
            <Bullet>
              <strong>Fases del pipeline</strong>: preprocess, forward, error computation, anomaly scoring.
              Permite identificar dónde se concentra el coste computacional.
            </Bullet>
            <Bullet>
              <strong>Datapoints procesados/segundo</strong> y aceleración respecto a la tasa de muestreo
              actual.
            </Bullet>
          </ul>
        </SubSection>
      </Section>

      {/* 4. Training methodology */}
      <Section icon={Brain} title="4. Metodología — Entrenamiento">
        <SubSection title="Grid del sweep">
          <Para>
            <strong>3 modelos × 5 batch sizes × 5 nodos × 5 volúmenes de dataset = 375 configuraciones</strong>
            por dispositivo. El grid es idéntico en todos los dispositivos para garantizar comparabilidad.
          </Para>
          <ul className="space-y-1.5">
            <Bullet>
              <strong>Arquitecturas</strong>: cognn, stgnn-gat, stgnn-topk
            </Bullet>
            <Bullet>
              <strong>Batch sizes</strong>: 4, 8, 16, 32, 64 (16 = referencia del calculator)
            </Bullet>
            <Bullet>
              <strong>Nodos</strong>: 20, 50, 100, 200, 500
            </Bullet>
            <Bullet>
              <strong>Muestras de dataset</strong>: 425, 850, 1700, 4250, 8500 (ajuste empírico al tamaño real
              de las particiones train/val)
            </Bullet>
          </ul>
        </SubSection>

        <SubSection title="Métricas registradas">
          <ul className="space-y-1.5">
            <Bullet>
              <strong>Throughput</strong>: muestras/segundo. Métrica primaria de tiempo de entrenamiento.
            </Bullet>
            <Bullet>
              <strong>Memoria desglosada</strong>: baseline, post-load, post-warmup, peak. Datos del modelo y
              del dataset por componente (x_train, y_train, x_val, y_val).
            </Bullet>
            <Bullet>
              <strong>Fases</strong>: data prep, forward, backward, optimizer.
            </Bullet>
            <Bullet>
              Las configuraciones que provocan OOM se capturan como{" "}
              <code className="text-primary font-mono text-[10px]">status: "error"</code>, lo que permite
              mapear la frontera exacta de viabilidad.
            </Bullet>
          </ul>
        </SubSection>
      </Section>

      {/* 5. Viability criteria */}
      <Section icon={Shield} title="5. Criterios de viabilidad">
        <Para>
          La viabilidad se evalúa en dos dimensiones independientes — <strong>latencia</strong> y{" "}
          <strong>memoria</strong> — que deben cumplirse simultáneamente.
        </Para>

        <SubSection title="Inferencia">
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="text-text-muted border-b border-border">
                  <th className="text-left py-2 pr-3 font-semibold">Veredicto</th>
                  <th className="text-left py-2 px-3 font-semibold">Budget ratio (latencia)</th>
                  <th className="text-left py-2 pl-3 font-semibold">Memory ratio</th>
                </tr>
              </thead>
              <tbody className="text-text-secondary">
                <tr className="border-b border-border/40"><td className="py-1.5 pr-3 text-excellent font-medium">Excellent</td><td className="py-1.5 px-3 font-mono">≤ 0.25</td><td className="py-1.5 pl-3 font-mono">≤ 0.80</td></tr>
                <tr className="border-b border-border/40"><td className="py-1.5 pr-3 text-viable font-medium">Viable</td><td className="py-1.5 px-3 font-mono">≤ 0.50</td><td className="py-1.5 pl-3 font-mono">≤ 0.80</td></tr>
                <tr className="border-b border-border/40"><td className="py-1.5 pr-3 text-tight font-medium">Tight</td><td className="py-1.5 px-3 font-mono">≤ 0.80</td><td className="py-1.5 pl-3 font-mono">≤ 0.90</td></tr>
                <tr><td className="py-1.5 pr-3 text-not-viable font-medium">Not viable</td><td className="py-1.5 px-3 font-mono">{">"} 0.80</td><td className="py-1.5 pl-3 font-mono">{">"} 0.90</td></tr>
              </tbody>
            </table>
          </div>
          <Para>
            <strong>Budget ratio</strong> = latencia P95 / presupuesto temporal de la ventana ETL. Margen del
            75% sobre la ventana en el caso{" "}
            <em>Excellent</em> protege contra variabilidad y overhead de IO.
            <br />
            <strong>Memory ratio</strong> = RSS peak / RAM disponible. El umbral 0.90 (no 1.0) protege contra
            la activación del OOM killer, picos transitorios y crecimiento del consumo de otros servicios.
          </Para>
        </SubSection>

        <SubSection title="Entrenamiento">
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="text-text-muted border-b border-border">
                  <th className="text-left py-2 pr-3 font-semibold">Veredicto</th>
                  <th className="text-left py-2 pl-3 font-semibold">RSS estimado / RAM disponible</th>
                </tr>
              </thead>
              <tbody className="text-text-secondary">
                <tr className="border-b border-border/40"><td className="py-1.5 pr-3 text-viable font-medium">Viable</td><td className="py-1.5 pl-3 font-mono">≤ 0.80</td></tr>
                <tr className="border-b border-border/40"><td className="py-1.5 pr-3 text-tight font-medium">Tight</td><td className="py-1.5 pl-3 font-mono">≤ 0.95</td></tr>
                <tr><td className="py-1.5 pr-3 text-not-viable font-medium">Not viable</td><td className="py-1.5 pl-3 font-mono">{">"} 0.95</td></tr>
              </tbody>
            </table>
          </div>
          <Para>
            Umbrales más permisivos que en inferencia porque el entrenamiento es un proceso batch: si falla
            por OOM se reintenta con parámetros reducidos; en inferencia un fallo significa pérdida de
            monitorización.
          </Para>
        </SubSection>

        <SubSection title="RAM disponible">
          <div className="bg-bg rounded-lg px-4 py-3 border border-border/60 font-mono text-xs text-text">
            RAM_disponible = RAM_total − stack_overhead
          </div>
          <Para>
            El <code className="text-primary font-mono text-[10px]">stack_overhead</code> se mide
            empíricamente para cada dispositivo ejecutando el stack completo de producción sin el servicio de
            ML.
          </Para>
        </SubSection>
      </Section>

      {/* Footer note */}
      <div className="bg-surface border border-border rounded-lg px-5 py-3">
        <p className="text-[11px] text-text-muted italic">
          Esta calculadora muestra exclusivamente datos empíricos medidos en cada dispositivo en los puntos del
          grid común N ∈ {"{20, 50, 100, 200, 500}"}. No se aplican modelos de regresión, ajustes paramétricos
          ni proyecciones extrapoladas: cada valor visualizado proviene directamente de un experimento
          ejecutado en hardware real.
        </p>
      </div>
    </div>
  );
}
