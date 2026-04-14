import { useState } from "react";
import type { DeviceData, ModelId } from "../../lib/types";
import type { DeviceResults } from "../../hooks/useSizingCalc";
import { useI18n } from "../../lib/i18n";
import { VerdictBadge } from "../ui/VerdictBadge";
import { DataBadge } from "../ui/DataBadge";
import { Tip } from "../ui/Tip";
import { PhaseBreakdown } from "../charts/PhaseBreakdown";
import { findTrainingByBatchSize, trainingThroughputCI, REFERENCE_BATCH_SIZE } from "../../lib/calculations";
import { Shield, ChevronDown, ChevronRight } from "lucide-react";

const MODELS: ModelId[] = ["cognn", "stgnn-gat", "stgnn-topk"];
const MODEL_LABELS: Record<ModelId, string> = {
  cognn: "CoGNN", "stgnn-gat": "STGNN-GAT", "stgnn-topk": "STGNN-TopK",
};

const PHASE_COLORS = {
  forward: "#0891B2",
  backward: "#F87171",
  optimizer: "#D97706",
  data_prep: "#94A3B8",
};

function fmtTime(s: number): string {
  if (s < 60) return `${s.toFixed(0)}s`;
  if (s < 3600) return `${(s / 60).toFixed(1)} min`;
  return `${(s / 3600).toFixed(1)}h`;
}


interface TrainingTabProps {
  results: DeviceResults[];
  devices: DeviceData[];
  numNodes: number;
  datasetSize: number;
  epochs: number;
}

export function TrainingTab({ results, devices, numNodes, datasetSize, epochs }: TrainingTabProps) {
  const { t } = useI18n();

  // Find the fastest viable training across all selected devices
  let bestTime = Infinity;
  let bestDeviceName = "";
  for (const dr of results) {
    const device = devices.find((d) => d.meta.device_id === dr.deviceId);
    if (!device) continue;
    for (const model of MODELS) {
      const tr = dr.training[model];
      if (tr && tr.verdict !== "not_viable" && tr.timeTotalS < bestTime) {
        bestTime = tr.timeTotalS;
        bestDeviceName = device.meta.device_name;
      }
    }
  }

  return (
    <div className="space-y-5">
      {/* Sovereignty banner — Act 5 headline */}
      <div className="bg-surface border border-border rounded-lg">
        <div className="px-5 py-4 flex items-start gap-4">
          <Shield size={20} className="text-excellent shrink-0 mt-0.5" />
          <div className="space-y-1.5 min-w-0">
            <p className="text-sm text-text leading-snug font-medium">
              {t("trainSovereignty")}
            </p>
            {bestTime < Infinity && (
              <p className="text-sm text-text-secondary leading-snug">
                {t("trainHeadline")
                  .replace("{epochs}", String(epochs))
                  .replace("{dataset}", datasetSize.toLocaleString())
                  .replace("{time}", fmtTime(bestTime))
                  .replace("{device}", bestDeviceName)}
              </p>
            )}
            <p className="text-xs text-excellent font-medium">{t("trainNoCloud")}</p>
          </div>
        </div>
      </div>

      {/* Per-device cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {results.map((dr) => {
          const device = devices.find((d) => d.meta.device_id === dr.deviceId);
          if (!device) return null;
          return (
            <DeviceTrainingCard
              key={dr.deviceId}
              device={device}
              dr={dr}
              numNodes={numNodes}
              datasetSize={datasetSize}
              epochs={epochs}
            />
          );
        })}
      </div>
    </div>
  );
}

// ─── Device card with summary table + collapsible technical detail ───

interface DeviceTrainingCardProps {
  device: DeviceData;
  dr: DeviceResults;
  numNodes: number;
  datasetSize: number;
  epochs: number;
}

function closestMeasuredSamples(device: DeviceData, target: number): number {
  const samples = device.meta.measured_num_samples;
  if (samples.length === 0) return target;
  return samples.reduce((best, s) => Math.abs(s - target) < Math.abs(best - target) ? s : best, samples[0]!);
}

function DeviceTrainingCard({ device, dr, numNodes, datasetSize, epochs }: DeviceTrainingCardProps) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-surface border border-border rounded-lg">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-text">{device.meta.device_name}</div>
          <div className="text-[10px] text-text-muted">
            {device.meta.ram_total_gb}GB · {device.meta.arch}
            {device.meta.cuda_version ? ` · CUDA ${device.meta.cuda_version}` : ""}
          </div>
        </div>
        <div className="text-[10px] text-text-muted">
          {epochs} ep. · {datasetSize.toLocaleString()} samples · {numNodes} {t("sensorsLabel")}
        </div>
      </div>

      {/* Summary table: one row per model */}
      <div>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text-muted">
              <th className="text-left py-2 px-4 font-medium">Model</th>
              <th className="text-right py-2 px-2 font-medium"><Tip text={t("tipThroughput")}>{t("throughput")}</Tip></th>
              <th className="text-right py-2 px-2 font-medium"><Tip text={t("tipPerEpoch")}>{t("perEpoch")}</Tip></th>
              <th className="text-right py-2 px-2 font-medium"><Tip text={t("tipTotal")}>{t("total")}</Tip></th>
              <th className="text-right py-2 px-2 font-medium"><Tip text={t("tipIncrement")}>+ Training</Tip></th>
              <th className="text-right py-2 px-4 font-medium"><Tip text={t("tipRssTotal")}>RAM total</Tip></th>
            </tr>
          </thead>
          <tbody>
            {/* Baseline row — system base (stack overhead) */}
            {(() => {
              const stackOverhead = device.meta.stack_overhead_mb;
              return (
                <tr className="border-t border-border/60 bg-bg/50">
                  <td className="py-1.5 px-4 text-text-muted" colSpan={4}>
                    <span className="text-[10px]">
                      Base del sistema (todos los servicios) = <span className="font-mono">{stackOverhead.toFixed(0)} MB</span>
                    </span>
                  </td>
                  <td className="py-1.5 px-2 text-right font-mono text-text-muted text-[10px]">base</td>
                  <td className="py-1.5 px-4 text-right font-mono text-text-muted text-[10px]">{stackOverhead.toFixed(0)} MB</td>
                </tr>
              );
            })()}
            {MODELS.map((model) => {
              const tr = dr.training[model];
              if (!tr) return null;
              const closestSamples = closestMeasuredSamples(device, datasetSize);
              const ci = trainingThroughputCI(device, model, numNodes, closestSamples);

              const increment = tr.rssEstimatedMb - tr.rssBaselineMb;
              const globalRss = device.meta.stack_overhead_mb + tr.rssEstimatedMb;

              return (
                <tr key={model} className="border-t border-border/60">
                  <td className="py-2 px-4">
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium text-text">{MODEL_LABELS[model]}</span>
                      <VerdictBadge verdict={tr.verdict} />
                    </div>
                  </td>
                  <td className="py-2 px-2 text-right font-mono text-text-secondary">
                    <span>{tr.throughputSps.toFixed(0)}</span>
                    {ci && ci.min !== ci.max && (
                      <span className="text-text-muted text-[10px] ml-1">
                        ({ci.min.toFixed(0)}–{ci.max.toFixed(0)})
                      </span>
                    )}
                  </td>
                  <td className="py-2 px-2 text-right font-mono text-text-secondary">
                    {fmtTime(tr.timePerEpochS)}
                  </td>
                  <td className="py-2 px-2 text-right font-mono font-semibold text-text">
                    {fmtTime(tr.timeTotalS)}
                  </td>
                  <td className="py-2 px-2 text-right font-mono text-primary">
                    +{increment.toFixed(0)} MB
                  </td>
                  <td className="py-2 px-4 text-right">
                    <span className="font-mono text-text">{globalRss.toFixed(0)} MB</span>
                    <span className="text-[10px] text-text-muted ml-1">
                      / {(device.meta.ram_total_gb * 1024).toFixed(0)}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Data provenance */}
      <div className="px-4 py-2 border-t border-border/60 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <DataBadge source="measured" />
          <span className="text-[10px] text-text-muted">{t("throughput")}, RAM</span>
          <DataBadge source="calculated" />
          <span className="text-[10px] text-text-muted">{t("perEpoch")}, {t("total")}</span>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 text-[10px] text-text-muted hover:text-text-secondary cursor-pointer"
        >
          {t("trainTechnicalDetail")}
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </button>
      </div>

      {/* Collapsible technical detail */}
      {expanded && (
        <div className="px-4 pb-4 pt-2 border-t border-border/40 space-y-4">
          {MODELS.map((model) => {
            const tr = dr.training[model];
            const bench = findTrainingByBatchSize(device, model, numNodes, REFERENCE_BATCH_SIZE);
            if (!tr || !bench) return null;

            return (
              <div key={model} className="space-y-2">
                <h4 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">{MODEL_LABELS[model]}</h4>
                <PhaseBreakdown phases={[
                  { name: "Forward", pct: bench.phases.forward_pct, color: PHASE_COLORS.forward },
                  { name: "Backward", pct: bench.phases.backward_pct, color: PHASE_COLORS.backward },
                  { name: "Optimizer", pct: bench.phases.optimizer_pct, color: PHASE_COLORS.optimizer },
                  { name: "Data prep", pct: bench.phases.data_prep_pct, color: PHASE_COLORS.data_prep },
                ]} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
