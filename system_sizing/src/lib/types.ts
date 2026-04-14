export type ModelId = "cognn" | "stgnn-gat" | "stgnn-topk";
export type Verdict = "excellent" | "viable" | "tight" | "not_viable";
export type DataSource = "measured" | "calculated";
export type PlatformType = "rpi" | "jetson" | "desktop";
export type Arch = "arm64" | "x86";

export interface DeviceMeta {
  device_id: string;
  device_name: string;
  device_tree_model: string;
  arch: Arch;
  ram_total_gb: number;
  gpu_model: string | null;
  gpu_vram_gb: number | null;
  cuda_version: string | null;
  platform_type: PlatformType;
  stack_overhead_mb: number;
  measured_node_counts: number[];
  measured_num_samples: number[];
  benchmark_date: string;
  schema_versions: { inference: string; training: string };
  software: { pytorch_version: string; python_version: string };
}

export interface LatencyStats {
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  mean_ms: number;
  std_ms: number;
  min_ms: number;
  max_ms: number;
}

export interface ColdStart {
  total_ms: number;
  model_init_ms: number;
  artifact_init_ms: number;
  first_inference_ms: number;
}

export interface InferenceBenchmark {
  model: ModelId;
  num_nodes: number;
  latency: LatencyStats;
  cold_start: ColdStart;
  memory: {
    rss_peak_mb: number;
    rss_baseline_mb: number;
    rss_after_init_mb: number;
    model_analytical_mb: number;
  };
  phases: {
    preprocess_pct: number;
    forward_pct: number;
    error_computation_pct: number;
    anomaly_scoring_pct: number;
  };
  cpu_utilization_mean_pct: number;
  datapoints_per_sec: number;
  config: {
    seq_in_len: number;
    batch_size: number;
    num_iterations: number;
    warmup_iterations: number;
  };
}

export interface TrainingBenchmark {
  model: ModelId;
  num_nodes: number;
  batch_size: number;
  num_samples: number;
  throughput_samples_per_sec: number;
  datapoints_per_sec: number;
  latency: { mean_ms: number; p50_ms: number; p95_ms: number };
  memory: {
    rss_peak_mb: number;
    rss_baseline_mb: number;
    rss_after_load_mb: number;
    rss_after_warmup_mb: number;
    data_total_mb: number;
    data_detail: {
      x_train_mb: number;
      y_train_mb: number;
      x_val_mb: number;
      y_val_mb: number;
    };
    model_total_mb: number;
    system_ram_used_mb: number;
  };
  phases: {
    forward_pct: number;
    backward_pct: number;
    optimizer_pct: number;
    data_prep_pct: number;
  };
  recommended_batch_size: boolean;
}

export interface DeviceData {
  meta: DeviceMeta;
  inference: InferenceBenchmark[];
  training: TrainingBenchmark[];
}

export interface SizingParams {
  numNodes: number;
  rateActualSeconds: number;
  etlBucketSeconds: number;
  datasetSize: number;
  epochs: number;
  selectedDeviceIds: string[];
  activeTab: string;
  lang: "es" | "en";
}

export interface InferenceResult {
  model: ModelId;
  /** Primary latency metric for sizing decisions — p95 is conservative for SLA
   * without being dominated by tail noise (p99 has only ~1 sample in n=100). */
  latencyP95Ms: number;
  /** Worst-case informative (kept for tooltip / diagnostic displays). */
  latencyP99Ms: number;
  coldStartMs: number;
  rssPeakMb: number;
  datapointsPerSec: number;
  budgetRatio: number;
  memoryRatio: number;
  accelerationFactor: number;
  verdict: Verdict;
}

export interface TrainingResult {
  model: ModelId;
  throughputSps: number;
  datapointsPerSec: number;
  recommendedBatchSize: number;
  timePerEpochS: number;
  timeTotalS: number;
  rssEstimatedMb: number;
  rssBaselineMb: number;
  ramAvailableMb: number;
  verdict: Verdict;
}
