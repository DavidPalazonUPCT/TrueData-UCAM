import { describe, it, expect } from "vitest";
import { deviceDataSchema } from "../src/lib/schema";

const MINIMAL_DEVICE: unknown = {
  meta: {
    device_id: "test-device",
    device_name: "Test Device",
    device_tree_model: "Test Model",
    arch: "arm64",
    ram_total_gb: 16,
    gpu_model: null,
    gpu_vram_gb: null,
    cuda_version: null,
    platform_type: "rpi",
    stack_overhead_mb: 3000,
    measured_node_counts: [20, 50, 100],
    measured_num_samples: [425, 850],
    benchmark_date: "2026-03-30",
    schema_versions: { inference: "2.1", training: "3.2" },
    software: { pytorch_version: "2.10.0", python_version: "3.12.13" },
  },
  inference: [
    {
      model: "cognn",
      num_nodes: 20,
      latency: { p50_ms: 128, p95_ms: 232, p99_ms: 339, mean_ms: 148, std_ms: 47, min_ms: 123, max_ms: 398 },
      cold_start: { total_ms: 2658, model_init_ms: 2528, artifact_init_ms: 1.8, first_inference_ms: 128 },
      memory: { rss_peak_mb: 471, rss_baseline_mb: 285, rss_after_init_mb: 471, model_analytical_mb: 0.018 },
      phases: { preprocess_pct: 0.1, forward_pct: 99.6, error_computation_pct: 0.1, anomaly_scoring_pct: 0.3 },
      cpu_utilization_mean_pct: 56,
      datapoints_per_sec: 135.1,
      config: { seq_in_len: 12, batch_size: 1, num_iterations: 100, warmup_iterations: 25 },
    },
  ],
  training: [
    {
      model: "cognn",
      num_nodes: 20,
      batch_size: 4,
      num_samples: 425,
      throughput_samples_per_sec: 18.55,
      datapoints_per_sec: 371,
      latency: { mean_ms: 215, p50_ms: 195, p95_ms: 285 },
      memory: {
        rss_peak_mb: 480, rss_baseline_mb: 408, rss_after_load_mb: 455, rss_after_warmup_mb: 479,
        data_total_mb: 0.496, data_detail: { x_train_mb: 0.389, y_train_mb: 0.032, x_val_mb: 0.069, y_val_mb: 0.006 },
        model_total_mb: 0.019, system_ram_used_mb: 4148,
      },
      phases: { forward_pct: 73.7, backward_pct: 22.6, optimizer_pct: 3.7, data_prep_pct: 0.0 },
      recommended_batch_size: true,
    },
  ],
};

describe("deviceDataSchema", () => {
  it("validates a correct device JSON", () => {
    const result = deviceDataSchema.safeParse(MINIMAL_DEVICE);
    expect(result.success).toBe(true);
  });

  it("rejects unknown model id", () => {
    const bad = structuredClone(MINIMAL_DEVICE) as Record<string, unknown>;
    (bad as { inference: Array<{ model: string }> }).inference[0]!.model = "unknown-model";
    const result = deviceDataSchema.safeParse(bad);
    expect(result.success).toBe(false);
  });

  it("rejects missing meta fields", () => {
    const bad = structuredClone(MINIMAL_DEVICE) as Record<string, Record<string, unknown>>;
    delete bad["meta"]!["device_id"];
    const result = deviceDataSchema.safeParse(bad);
    expect(result.success).toBe(false);
  });
});
