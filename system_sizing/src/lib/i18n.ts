import { useSyncExternalStore, useCallback } from "react";

type Lang = "es" | "en";

const strings = {
  es: {
    title: "TrueData System Sizing",
    subtitle: "Dimensionamiento de hardware edge — Proyecto INCIBE",
    plantConfig: "Tu planta",
    sensors: "Sensores",
    currentRate: "Rate actual (s)",
    sampleFaster: "Puedes muestrear mas rapido?",
    etlBucket: "Ventana ETL (s)",
    trainingProjection: "Configuracion operacional",
    datasetSize: "Dataset historico",
    epochs: "Epocas",
    devices: "Dispositivos",
    recommendation: "Recomendacion",
    fasterThan: "mas rapido",
    overview: "Overview",
    inference: "Inferencia",
    training: "Training",
    hardware: "Hardware",
    methodology: "Metodologia",
    measured: "medido",
    calculated: "calculado",
    estimated: "estimado",
    excellent: "Excelente",
    viable: "Viable",
    tight: "Ajustado",
    not_viable: "No viable",
    noData: "No hay datos de benchmark disponibles.",
    noViable: "Sin configuracion viable para estos parametros.",
    accelerationBanner: "El sistema procesa datos {factor}x mas rapido que tu monitorizacion actual",
    accelerationInvite: "Y si muestreaseis cada {rate}s? El sistema seguiria procesando sin problema.",
    accelerationMax: "Estais aprovechando la capacidad al maximo.",
    temporalResolution: "Con muestreo cada {current}s, detectais una anomalia en <={current}s. Con muestreo cada {target}s, en <={target}s.",
    timesteps: "timesteps",
    samplesPerSec: "muestras/s",
    coldStart: "Cold start",
    latencyP95: "Latencia P95",
    latencyP99: "Latencia P99",
    rssPeak: "RSS peak",
    trainTime: "Tiempo training",
    batchSize: "Batch size recom.",
    ramAvailable: "RAM disponible",
    sensorsLabel: "sensores",
    perEpoch: "por epoca",
    total: "total",
    throughput: "Throughput",
    datapoints: "Datapoints/s",
    memoryUsage: "Uso memoria",
    phases: "Fases",
    cpuUtil: "CPU util.",
    specs: "Especificaciones",
    benchmarkDate: "Fecha benchmark",
    trainSovereignty: "El entrenamiento se ejecuta directamente en el dispositivo. Los datos de tu planta nunca salen de tu red.",
    trainHeadline: "{epochs} epocas x {dataset} muestras → {time} en {device}",
    trainNoCloud: "Sin cloud. Sin transferencia de datos. Soberania total.",
    trainFits: "Cabe en memoria",
    trainDoesNotFit: "Requiere mas RAM — delegar a servidor",
    trainTechnicalDetail: "Detalle tecnico",
    tipP95: "Latencia percentil 95 — metrica primaria de sizing (conservadora sin ruido de cola)",
    tipP99: "Latencia percentil 99 de una inferencia completa (peor caso informativo)",
    tipAccel: "Cuantas veces mas rapido que tu tasa de muestreo actual",
    tipTrainTime: "Tiempo total estimado de entrenamiento",
    tipThroughput: "Muestras procesadas por segundo (bs=16)",
    tipPerEpoch: "Tiempo para 1 pasada completa del dataset",
    tipTotal: "Tiempo total para todas las epocas configuradas",
    tipIncrement: "Memoria adicional sobre el baseline de PyTorch",
    tipRssTotal: "Memoria total: runtime + modelo + datos",
    tipRamPct: "Porcentaje de RAM disponible utilizado",
  },
  en: {
    title: "TrueData System Sizing",
    subtitle: "Edge hardware dimensioning — INCIBE project",
    plantConfig: "Your plant",
    sensors: "Sensors",
    currentRate: "Current rate (s)",
    sampleFaster: "Can you sample faster?",
    etlBucket: "ETL bucket window (s)",
    trainingProjection: "Operational configuration",
    datasetSize: "Historical dataset",
    epochs: "Epochs",
    devices: "Devices",
    recommendation: "Recommendation",
    fasterThan: "faster",
    overview: "Overview",
    inference: "Inference",
    training: "Training",
    hardware: "Hardware",
    methodology: "Methodology",
    measured: "measured",
    calculated: "calculated",
    estimated: "estimated",
    excellent: "Excellent",
    viable: "Viable",
    tight: "Tight",
    not_viable: "Not viable",
    noData: "No benchmark data available.",
    noViable: "No viable configuration for these parameters.",
    accelerationBanner: "The system processes data {factor}x faster than your current monitoring",
    accelerationInvite: "What if you sampled every {rate}s? The system would still handle it.",
    accelerationMax: "You are using the full capacity.",
    temporalResolution: "Sampling every {current}s: anomaly detected in <={current}s. Every {target}s: in <={target}s.",
    timesteps: "timesteps",
    samplesPerSec: "samples/s",
    coldStart: "Cold start",
    latencyP95: "Latency P95",
    latencyP99: "Latency P99",
    rssPeak: "RSS peak",
    trainTime: "Training time",
    batchSize: "Recom. batch size",
    ramAvailable: "Available RAM",
    sensorsLabel: "sensors",
    perEpoch: "per epoch",
    total: "total",
    throughput: "Throughput",
    datapoints: "Datapoints/s",
    memoryUsage: "Memory usage",
    phases: "Phases",
    cpuUtil: "CPU util.",
    specs: "Specifications",
    benchmarkDate: "Benchmark date",
    trainSovereignty: "Training runs directly on the device. Your plant data never leaves your network.",
    trainHeadline: "{epochs} epochs x {dataset} samples → {time} on {device}",
    trainNoCloud: "No cloud. No data transfer. Full sovereignty.",
    trainFits: "Fits in memory",
    trainDoesNotFit: "Needs more RAM — delegate to server",
    trainTechnicalDetail: "Technical detail",
    tipP95: "95th percentile latency — primary sizing metric (conservative without tail noise)",
    tipP99: "99th percentile latency for a full inference pass (worst-case informational)",
    tipAccel: "How many times faster than your current sampling rate",
    tipTrainTime: "Estimated total training time",
    tipThroughput: "Samples processed per second (bs=16)",
    tipPerEpoch: "Time for 1 full pass through the dataset",
    tipTotal: "Total time for all configured epochs",
    tipIncrement: "Memory added on top of PyTorch baseline",
    tipRssTotal: "Total memory: runtime + model + data",
    tipRamPct: "Percentage of available RAM used",
  },
} as const;

export type StringKey = keyof (typeof strings)["es"];

let currentLang: Lang = "es";
const listeners = new Set<() => void>();

function emitChange() {
  listeners.forEach((fn) => fn());
}

export function setLang(lang: Lang) {
  currentLang = lang;
  emitChange();
}

export function getLang(): Lang {
  return currentLang;
}

export function t(key: StringKey): string {
  return strings[currentLang][key];
}

export function useI18n() {
  const lang = useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    () => currentLang,
  );
  const translate = useCallback((key: StringKey) => strings[lang][key], [lang]);
  return { lang, t: translate, setLang };
}
