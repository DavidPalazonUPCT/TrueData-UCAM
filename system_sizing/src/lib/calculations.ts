import type {
  Verdict,
  ModelId,
  DeviceData,
  InferenceResult,
  TrainingResult,
  InferenceBenchmark,
  TrainingBenchmark,
} from "./types";

export function inferenceVerdict(budgetRatio: number, memoryRatio: number): Verdict {
  if (budgetRatio > 0.80 || memoryRatio > 0.90) return "not_viable";
  if (budgetRatio > 0.50 || memoryRatio > 0.80) return "tight";
  if (budgetRatio > 0.25) return "viable";
  return "excellent";
}

export function trainingVerdict(rssEstimatedMb: number, ramAvailableMb: number): Verdict {
  const ratio = rssEstimatedMb / ramAvailableMb;
  if (ratio > 0.95) return "not_viable";
  if (ratio > 0.80) return "tight";
  return "viable";
}

export function calcRamAvailable(ramTotalGb: number, stackOverheadMb: number): number {
  return ramTotalGb * 1024 - stackOverheadMb;
}

export function calcAccelerationFactor(
  datapointsTruedata: number,
  numSensors: number,
  rateActualSeconds: number,
): number {
  const datapointsActual = numSensors / rateActualSeconds;
  return datapointsTruedata / datapointsActual;
}

export function calcTrainingTime(
  datasetSize: number,
  throughputSps: number,
  epochs: number,
): { timePerEpochS: number; timeTotalS: number } {
  const timePerEpochS = datasetSize / throughputSps;
  return { timePerEpochS, timeTotalS: timePerEpochS * epochs };
}

export function findInferenceBenchmark(
  data: DeviceData,
  model: ModelId,
  numNodes: number,
): InferenceBenchmark | undefined {
  return data.inference.find(
    (b) => b.model === model && b.num_nodes === numNodes,
  );
}

export const REFERENCE_BATCH_SIZE = 16;

export function findRecommendedTraining(
  data: DeviceData,
  model: ModelId,
  numNodes: number,
): TrainingBenchmark | undefined {
  return data.training.find(
    (b) => b.model === model && b.num_nodes === numNodes && b.recommended_batch_size,
  );
}

export function findTrainingByBatchSize(
  data: DeviceData,
  model: ModelId,
  numNodes: number,
  batchSize: number = REFERENCE_BATCH_SIZE,
): TrainingBenchmark | undefined {
  return data.training.find(
    (b) => b.model === model && b.num_nodes === numNodes && b.batch_size === batchSize,
  );
}

/**
 * Get throughput stats across all batch sizes for a given (model, numNodes, numSamples).
 * Returns the bs=16 value as reference, plus min/max from other batch sizes as CI.
 */
export function trainingThroughputCI(
  data: DeviceData,
  model: ModelId,
  numNodes: number,
  numSamples: number,
): { ref: number; min: number; max: number; batchSizes: number[] } | null {
  const candidates = data.training.filter(
    (b) => b.model === model && b.num_nodes === numNodes && b.num_samples === numSamples,
  );
  if (candidates.length === 0) return null;

  const ref = candidates.find((b) => b.batch_size === REFERENCE_BATCH_SIZE);
  const throughputs = candidates.map((b) => b.throughput_samples_per_sec);
  const batchSizes = candidates.map((b) => b.batch_size);

  return {
    ref: ref?.throughput_samples_per_sec ?? candidates[0]!.throughput_samples_per_sec,
    min: Math.min(...throughputs),
    max: Math.max(...throughputs),
    batchSizes,
  };
}

export function findClosestTrainingMemory(
  data: DeviceData,
  model: ModelId,
  numNodes: number,
  batchSize: number,
  userDatasetSize: number,
): TrainingBenchmark | undefined {
  const candidates = data.training
    .filter((b) => b.model === model && b.num_nodes === numNodes && b.batch_size === batchSize)
    .sort((a, b) => a.num_samples - b.num_samples);
  return candidates.find((b) => b.num_samples >= userDatasetSize) ?? candidates.at(-1);
}

export function calcInferenceResult(
  benchmark: InferenceBenchmark,
  ramAvailableMb: number,
  etlBucketSeconds: number,
  numSensors: number,
  rateActualSeconds: number,
): InferenceResult {
  const etlBudgetMs = etlBucketSeconds * 1000;
  // Primary sizing metric is p95 — conservative for SLA without being dominated
  // by tail noise (p99 has only ~1 observation in n=100 iter per config).
  const budgetRatio = benchmark.latency.p95_ms / etlBudgetMs;
  const memoryRatio = benchmark.memory.rss_peak_mb / ramAvailableMb;
  const accelerationFactor = calcAccelerationFactor(
    benchmark.datapoints_per_sec,
    numSensors,
    rateActualSeconds,
  );

  return {
    model: benchmark.model,
    latencyP95Ms: benchmark.latency.p95_ms,
    latencyP99Ms: benchmark.latency.p99_ms,
    coldStartMs: benchmark.cold_start.total_ms,
    rssPeakMb: benchmark.memory.rss_peak_mb,
    datapointsPerSec: benchmark.datapoints_per_sec,
    budgetRatio,
    memoryRatio,
    accelerationFactor,
    verdict: inferenceVerdict(budgetRatio, memoryRatio),
  };
}

export function calcTrainingResult(
  recommended: TrainingBenchmark,
  memoryBenchmark: TrainingBenchmark | undefined,
  ramAvailableMb: number,
  datasetSize: number,
  epochs: number,
): TrainingResult {
  const { timePerEpochS, timeTotalS } = calcTrainingTime(
    datasetSize,
    recommended.throughput_samples_per_sec,
    epochs,
  );

  const rssEstimatedMb = memoryBenchmark?.memory.rss_peak_mb ?? recommended.memory.rss_peak_mb;
  const rssBaselineMb = memoryBenchmark?.memory.rss_baseline_mb ?? recommended.memory.rss_baseline_mb;

  return {
    model: recommended.model,
    throughputSps: recommended.throughput_samples_per_sec,
    datapointsPerSec: recommended.datapoints_per_sec,
    recommendedBatchSize: recommended.batch_size,
    timePerEpochS,
    timeTotalS,
    rssEstimatedMb,
    rssBaselineMb,
    ramAvailableMb,
    verdict: trainingVerdict(rssEstimatedMb, ramAvailableMb),
  };
}

const MODELS: ModelId[] = ["cognn", "stgnn-gat", "stgnn-topk"];

export function bestOption(
  devices: DeviceData[],
  numNodes: number,
  etlBucketSeconds: number,
  rateActualSeconds: number,
  _datasetSize: number,
  _epochs: number,
): { deviceId: string; model: ModelId } | null {
  let best: { deviceId: string; model: ModelId } | null = null;
  let bestScore = -Infinity;

  for (const device of devices) {
    const ramAvail = calcRamAvailable(device.meta.ram_total_gb, device.meta.stack_overhead_mb);
    for (const model of MODELS) {
      const inf = findInferenceBenchmark(device, model, numNodes);
      if (!inf) continue;
      const infResult = calcInferenceResult(inf, ramAvail, etlBucketSeconds, numNodes, rateActualSeconds);
      if (infResult.verdict === "not_viable") continue;

      const rec = findRecommendedTraining(device, model, numNodes);
      const trainVerdict_ = rec
        ? trainingVerdict(rec.memory.rss_peak_mb, ramAvail)
        : "not_viable" as const;

      const score =
        (1000 - infResult.latencyP95Ms) * 10 +
        (trainVerdict_ !== "not_viable" ? 5000 : 0) +
        (infResult.verdict === "excellent" ? 2000 : 0);

      if (score > bestScore) {
        bestScore = score;
        best = { deviceId: device.meta.device_id, model };
      }
    }
  }
  return best;
}
