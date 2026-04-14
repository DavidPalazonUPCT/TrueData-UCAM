import { z } from "zod";

const modelId = z.enum(["cognn", "stgnn-gat", "stgnn-topk"]);

const inferenceBenchmark = z.object({
  model: modelId,
  num_nodes: z.number().int().positive(),
  latency: z.object({
    p50_ms: z.number(), p95_ms: z.number(), p99_ms: z.number(),
    mean_ms: z.number(), std_ms: z.number(),
    min_ms: z.number(), max_ms: z.number(),
  }),
  cold_start: z.object({
    total_ms: z.number(), model_init_ms: z.number(),
    artifact_init_ms: z.number(), first_inference_ms: z.number(),
  }),
  memory: z.object({
    rss_peak_mb: z.number(), rss_baseline_mb: z.number(),
    rss_after_init_mb: z.number(), model_analytical_mb: z.number(),
  }),
  phases: z.object({
    preprocess_pct: z.number(), forward_pct: z.number(),
    error_computation_pct: z.number(), anomaly_scoring_pct: z.number(),
  }),
  cpu_utilization_mean_pct: z.number(),
  datapoints_per_sec: z.number(),
  config: z.object({
    seq_in_len: z.number(), batch_size: z.number(),
    num_iterations: z.number(), warmup_iterations: z.number(),
  }),
});

const trainingBenchmark = z.object({
  model: modelId,
  num_nodes: z.number().int().positive(),
  batch_size: z.number().int().positive(),
  num_samples: z.number().int().positive(),
  throughput_samples_per_sec: z.number(),
  datapoints_per_sec: z.number(),
  latency: z.object({
    mean_ms: z.number(), p50_ms: z.number(), p95_ms: z.number(),
  }),
  memory: z.object({
    rss_peak_mb: z.number(), rss_baseline_mb: z.number(),
    rss_after_load_mb: z.number(), rss_after_warmup_mb: z.number(),
    data_total_mb: z.number(),
    data_detail: z.object({
      x_train_mb: z.number(), y_train_mb: z.number(),
      x_val_mb: z.number(), y_val_mb: z.number(),
    }),
    model_total_mb: z.number(),
    system_ram_used_mb: z.number(),
  }),
  phases: z.object({
    forward_pct: z.number(), backward_pct: z.number(),
    optimizer_pct: z.number(), data_prep_pct: z.number(),
  }),
  recommended_batch_size: z.boolean(),
});

export const deviceDataSchema = z.object({
  meta: z.object({
    device_id: z.string(),
    device_name: z.string(),
    device_tree_model: z.string(),
    arch: z.enum(["arm64", "x86"]),
    ram_total_gb: z.number(),
    gpu_model: z.string().nullable(),
    gpu_vram_gb: z.number().nullable(),
    cuda_version: z.string().nullable(),
    platform_type: z.enum(["rpi", "jetson", "desktop"]),
    stack_overhead_mb: z.number(),
    measured_node_counts: z.array(z.number()),
    measured_num_samples: z.array(z.number()),
    benchmark_date: z.string(),
    schema_versions: z.object({ inference: z.string(), training: z.string() }),
    software: z.object({ pytorch_version: z.string(), python_version: z.string() }),
  }),
  inference: z.array(inferenceBenchmark),
  training: z.array(trainingBenchmark),
});
