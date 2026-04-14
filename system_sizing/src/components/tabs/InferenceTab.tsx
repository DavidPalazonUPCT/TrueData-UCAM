import { useState } from "react";
import type { DeviceData, ModelId } from "../../lib/types";
import type { DeviceResults } from "../../hooks/useSizingCalc";
import { useI18n } from "../../lib/i18n";
import { VerdictBadge } from "../ui/VerdictBadge";
import { MetricCard } from "../ui/MetricCard";
import { DataBadge } from "../ui/DataBadge";
import { Tip } from "../ui/Tip";
import { LatencyCurveChart } from "../charts/LatencyCurveChart";
import { PhaseBreakdown } from "../charts/PhaseBreakdown";
import { findInferenceBenchmark } from "../../lib/calculations";
import { ChevronDown, ChevronRight } from "lucide-react";

const MODELS: ModelId[] = ["cognn", "stgnn-gat", "stgnn-topk"];
const MODEL_LABELS: Record<ModelId, string> = {
  cognn: "CoGNN", "stgnn-gat": "STGNN-GAT", "stgnn-topk": "STGNN-TopK",
};
const MODEL_COLORS: Record<ModelId, string> = {
  cognn: "#F87171", "stgnn-gat": "#FBBF24", "stgnn-topk": "#34D399",
};
const PHASE_COLORS = {
  preprocess: "#94A3B8",
  forward: "#0891B2",
  error_computation: "#D97706",
  anomaly_scoring: "#34D399",
};

function formatMs(ms: number): string {
  if (ms < 1) return `${(ms * 1000).toFixed(0)}us`;
  if (ms < 1000) return `${ms.toFixed(1)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

interface InferenceTabProps {
  results: DeviceResults[];
  devices: DeviceData[];
  numNodes: number;
  etlBucket: number;
  rateActual: number;
}

export function InferenceTab({ results, devices, numNodes, etlBucket, rateActual }: InferenceTabProps) {
  const etlBudgetMs = etlBucket * 1000;

  return (
    <div className="space-y-4">
      {results.map((dr) => {
        const device = devices.find((d) => d.meta.device_id === dr.deviceId);
        if (!device) return null;

        return (
          <InferenceDeviceCard
            key={dr.deviceId}
            device={device}
            dr={dr}
            etlBudgetMs={etlBudgetMs}
            numNodes={numNodes}
            rateActual={rateActual}
          />
        );
      })}
    </div>
  );
}

interface InferenceDeviceCardProps {
  device: DeviceData;
  dr: DeviceResults;
  etlBudgetMs: number;
  numNodes: number;
  rateActual: number;
}

function InferenceDeviceCard({ device, dr, etlBudgetMs, numNodes, rateActual }: InferenceDeviceCardProps) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);

  const stack = device.meta.stack_overhead_mb;

  return (
    <div className="bg-surface border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left cursor-pointer"
      >
        <div className="px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {expanded ? <ChevronDown size={14} className="text-text-muted" /> : <ChevronRight size={14} className="text-text-muted" />}
            <div>
              <div className="text-sm font-semibold text-text">{device.meta.device_name}</div>
              <div className="text-[10px] text-text-muted">
                {device.meta.ram_total_gb}GB · {device.meta.arch}
                {device.meta.cuda_version ? ` · CUDA ${device.meta.cuda_version}` : ""}
              </div>
            </div>
          </div>
          <VerdictBadge verdict={dr.globalVerdict} />
        </div>
      </button>

      {/* Summary table — always visible */}
      <div className="border-t border-border/60">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text-muted">
              <th className="text-left py-1.5 pl-4 pr-1 font-medium">Modelo</th>
              <th className="text-right py-1.5 px-2 font-medium"><Tip text={t("tipP95")}>P95</Tip></th>
              <th className="text-right py-1.5 px-2 font-medium"><Tip text="Factor de aceleracion vs tasa de muestreo">Accel.</Tip></th>
              <th className="text-right py-1.5 px-2 font-medium"><Tip text="Datapoints procesados por segundo">dp/s</Tip></th>
              <th className="text-right py-1.5 px-2 font-medium"><Tip text="RAM sistema + proceso inferencia">RAM total</Tip></th>
              <th className="text-center py-1.5 pr-4 pl-1 font-medium">Estado</th>
            </tr>
          </thead>
          <tbody>
            {MODELS.map((model) => {
              const inf = dr.inference[model];
              if (!inf) return null;
              return (
                <tr key={model} className="border-t border-border/40">
                  <td className="py-2 pl-4 pr-1">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: MODEL_COLORS[model] }} />
                      <span className="font-medium text-text">{MODEL_LABELS[model]}</span>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-right font-mono text-text">{formatMs(inf.latencyP95Ms)}</td>
                  <td className="py-2 px-2 text-right font-mono font-semibold text-text">
                    {Math.round(inf.accelerationFactor).toLocaleString()}x
                  </td>
                  <td className="py-2 px-2 text-right font-mono text-text-secondary">
                    {inf.datapointsPerSec.toFixed(0)}
                  </td>
                  <td className="py-2 px-2 text-right">
                    <span className="font-mono text-text-secondary">{(stack + inf.rssPeakMb).toFixed(0)}</span>
                    <span className="text-[10px] text-text-muted ml-0.5">MB</span>
                  </td>
                  <td className="py-2 pr-4 pl-1 text-center">
                    <VerdictBadge verdict={inf.verdict} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Expanded: full detail */}
      {expanded && (
        <div className="border-t border-border">
          <div className="p-5 space-y-6">
            {/* Latency chart — empirical points only */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider">Latencia medida por nº de sensores</h4>
              <div className="flex items-center gap-4 text-[10px] text-text-muted">
                {MODELS.map((m) => (
                  <span key={m} className="flex items-center gap-1.5">
                    <span className="w-3 h-0.5 rounded" style={{ backgroundColor: MODEL_COLORS[m] }} />
                    {MODEL_LABELS[m]}
                  </span>
                ))}
                <span className="ml-auto">
                  <span className="inline-block w-4 border-t border-dashed border-not-viable mr-1" />
                  50% ETL budget
                </span>
              </div>
              <LatencyCurveChart
                benchmarks={device.inference}
                etlBudgetMs={etlBudgetMs}
                currentNodes={numNodes}
              />
              <p className="text-[10px] text-text-muted italic">
                Línea continua = P50 (mediana). Línea discontinua = P95. Solo se muestran puntos medidos en N={"{20, 50, 100, 200, 500}"}.
              </p>
            </div>

            {/* Per-model detailed metrics */}
            {MODELS.map((model) => {
              const inf = dr.inference[model];
              if (!inf) return null;

              return (
                <div key={model} className="border-t border-border/60 pt-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: MODEL_COLORS[model] }} />
                    <h4 className="text-xs font-semibold text-text">{MODEL_LABELS[model]}</h4>
                  </div>

                  <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                    <MetricCard label={t("latencyP95")} value={formatMs(inf.latencyP95Ms)} source="measured" verdict={inf.verdict} />
                    <MetricCard label={t("coldStart")} value={formatMs(inf.coldStartMs)} source="measured" />
                    <MetricCard label={t("datapoints")} value={`${inf.datapointsPerSec.toFixed(0)}/s`} source="measured" />
                    <MetricCard
                      label="Accel."
                      value={`${Math.round(inf.accelerationFactor).toLocaleString()}x`}
                      source="calculated"
                      sub={`vs ${rateActual}s`}
                    />
                    <MetricCard
                      label="RAM total"
                      value={`${(stack + inf.rssPeakMb).toFixed(0)} MB`}
                      source="measured"
                      sub={`${stack.toFixed(0)} + ${inf.rssPeakMb.toFixed(0)}`}
                    />
                  </div>
                </div>
              );
            })}

            {/* Phase breakdown */}
            <div className="border-t border-border/60 pt-4 space-y-4">
              <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider">Fases de inferencia</h4>
              {MODELS.map((model) => {
                const bench = findInferenceBenchmark(device, model, numNodes);
                if (!bench) return null;

                return (
                  <div key={model} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: MODEL_COLORS[model] }} />
                      <span className="text-[11px] font-semibold text-text-muted">{MODEL_LABELS[model]}</span>
                    </div>
                    <PhaseBreakdown phases={[
                      { name: "Preprocess", pct: bench.phases.preprocess_pct, color: PHASE_COLORS.preprocess },
                      { name: "Forward", pct: bench.phases.forward_pct, color: PHASE_COLORS.forward },
                      { name: "Error comp.", pct: bench.phases.error_computation_pct, color: PHASE_COLORS.error_computation },
                      { name: "Scoring", pct: bench.phases.anomaly_scoring_pct, color: PHASE_COLORS.anomaly_scoring },
                    ]} />
                  </div>
                );
              })}
            </div>
          </div>

          {/* Data provenance */}
          <div className="px-5 py-2 border-t border-border/60 flex items-center gap-2">
            <DataBadge source="measured" />
            <span className="text-[10px] text-text-muted">{t("latencyP95")}, {t("datapoints")}, RAM</span>
            <DataBadge source="calculated" />
            <span className="text-[10px] text-text-muted">Accel.</span>
          </div>
        </div>
      )}
    </div>
  );
}
