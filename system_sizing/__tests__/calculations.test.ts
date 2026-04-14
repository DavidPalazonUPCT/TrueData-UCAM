import { describe, it, expect } from "vitest";
import {
  inferenceVerdict,
  trainingVerdict,
  calcAccelerationFactor,
  calcTrainingTime,
  calcRamAvailable,
  calcTrainingResult,
} from "../src/lib/calculations";
import type { TrainingBenchmark } from "../src/lib/types";

describe("inferenceVerdict", () => {
  it("returns excellent when both ratios are low", () => {
    expect(inferenceVerdict(0.01, 0.3)).toBe("excellent");
  });
  it("returns viable when budget ratio is moderate", () => {
    expect(inferenceVerdict(0.30, 0.5)).toBe("viable");
  });
  it("returns tight when budget ratio exceeds 50%", () => {
    expect(inferenceVerdict(0.55, 0.5)).toBe("tight");
  });
  it("returns not_viable when budget ratio exceeds 80%", () => {
    expect(inferenceVerdict(0.85, 0.5)).toBe("not_viable");
  });
  it("returns not_viable when memory ratio exceeds 90%", () => {
    expect(inferenceVerdict(0.10, 0.95)).toBe("not_viable");
  });
});

describe("trainingVerdict", () => {
  it("returns viable when memory fits with margin", () => {
    expect(trainingVerdict(400, 1000)).toBe("viable");
  });
  it("returns tight when memory ratio > 80%", () => {
    expect(trainingVerdict(850, 1000)).toBe("tight");
  });
  it("returns not_viable when memory ratio > 95%", () => {
    expect(trainingVerdict(960, 1000)).toBe("not_viable");
  });
});

describe("calcAccelerationFactor", () => {
  it("calculates correct factor", () => {
    const result = calcAccelerationFactor(22222, 100, 30);
    expect(result).toBeCloseTo(6667, 0);
  });
});

describe("calcTrainingTime", () => {
  it("projects training time correctly", () => {
    const result = calcTrainingTime(10000, 18.55, 20);
    expect(result.timePerEpochS).toBeCloseTo(539.1, 0);
    expect(result.timeTotalS).toBeCloseTo(10780, -1);
  });
});

describe("calcRamAvailable", () => {
  it("subtracts stack overhead from total", () => {
    expect(calcRamAvailable(16, 3000)).toBeCloseTo(13384);
  });
});

function makeBench(overrides: Partial<TrainingBenchmark> = {}): TrainingBenchmark {
  return {
    model: "cognn",
    num_nodes: 100,
    batch_size: 16,
    num_samples: 8500,
    throughput_samples_per_sec: 18.55,
    datapoints_per_sec: 1855,
    latency: { mean_ms: 50, p50_ms: 48, p95_ms: 60 },
    memory: {
      rss_peak_mb: 789.1,
      rss_baseline_mb: 665.4,
      rss_after_load_mb: 700,
      rss_after_warmup_mb: 710,
      data_total_mb: 49.6,
      data_detail: { x_train_mb: 38.91, y_train_mb: 3.24, x_val_mb: 6.87, y_val_mb: 0.57 },
      model_total_mb: 0,
      system_ram_used_mb: 3000,
    },
    phases: { forward_pct: 40, backward_pct: 35, optimizer_pct: 15, data_prep_pct: 10 },
    recommended_batch_size: true,
    ...overrides,
  };
}

describe("calcTrainingResult", () => {
  const bench = makeBench();
  const ramAvail = 4500;

  it("uses measured RSS from memory benchmark", () => {
    const result = calcTrainingResult(bench, bench, ramAvail, 10000, 20);
    expect(result.rssEstimatedMb).toBe(789.1);
    expect(result.rssBaselineMb).toBe(665.4);
  });

  it("falls back to recommended bench RSS when memory bench is undefined", () => {
    const recommended = makeBench({ memory: { ...bench.memory, rss_peak_mb: 700, rss_baseline_mb: 600 } });
    const result = calcTrainingResult(recommended, undefined, ramAvail, 10000, 20);
    expect(result.rssEstimatedMb).toBe(700);
    expect(result.rssBaselineMb).toBe(600);
  });

  it("verdict reflects ratio against ram available", () => {
    const lowMem = makeBench({ memory: { ...bench.memory, rss_peak_mb: 3000 } });
    expect(calcTrainingResult(lowMem, lowMem, ramAvail, 10000, 20).verdict).toBe("viable");

    const highMem = makeBench({ memory: { ...bench.memory, rss_peak_mb: 4400 } });
    expect(calcTrainingResult(highMem, highMem, ramAvail, 10000, 20).verdict).toBe("not_viable");
  });
});
