import type { DeviceData, ModelId } from "../../lib/types";
import type { DeviceResults } from "../../hooks/useSizingCalc";
import { useI18n } from "../../lib/i18n";
import { VerdictBadge } from "../ui/VerdictBadge";
import { DataBadge } from "../ui/DataBadge";
import { Tip } from "../ui/Tip";
import { ParetoChart } from "../charts/ParetoChart";
import type { ParetoPoint } from "../charts/ParetoChart";
import { Zap } from "lucide-react";

const MODEL_LABELS: Record<ModelId, string> = {
  cognn: "CoGNN",
  "stgnn-gat": "STGNN-GAT",
  "stgnn-topk": "STGNN-TopK",
};
const MODELS: ModelId[] = ["cognn", "stgnn-gat", "stgnn-topk"];

function fmtMs(ms: number): string {
  if (ms < 1) return `${(ms * 1000).toFixed(0)}us`;
  if (ms < 1000) return `${ms.toFixed(1)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function fmtTime(s: number): string {
  if (s < 60) return `${s.toFixed(0)}s`;
  if (s < 3600) return `${(s / 60).toFixed(1)}min`;
  return `${(s / 3600).toFixed(1)}h`;
}

interface OverviewTabProps {
  results: DeviceResults[];
  devices: DeviceData[];
  rateActual: number;
  numNodes: number;
  etlBucket: number;
  recommendation: {
    deviceId: string;
    model: ModelId;
    accelerationFactor: number;
  } | null;
}

export function OverviewTab({ results, devices, rateActual, numNodes, etlBucket, recommendation }: OverviewTabProps) {
  const { t } = useI18n();

  const recDevice = recommendation
    ? devices.find((d) => d.meta.device_id === recommendation.deviceId)
    : null;

  return (
    <div className="space-y-5">
      {/* Recommendation hero */}
      {recommendation && recDevice && (
        <div className="bg-surface border border-border rounded-lg overflow-hidden">
          <div className="px-5 py-4 flex items-start justify-between gap-6">
            <div className="space-y-2 min-w-0">
              <div className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">{t("recommendation")}</div>
              <div className="text-base font-semibold text-text">
                {recDevice.meta.device_name} + {MODEL_LABELS[recommendation.model]}
              </div>
            </div>
            <div className="shrink-0 text-right">
              <div className="flex items-center gap-1.5 text-primary justify-end">
                <Zap size={16} />
                <span className="text-3xl font-mono font-bold leading-none">
                  {Math.round(recommendation.accelerationFactor).toLocaleString()}x
                </span>
              </div>
              <div className="text-[11px] text-text-muted mt-1">{t("fasterThan")}</div>
            </div>
          </div>
          {/* Contextual nudge */}
          {rateActual > 10 && (
            <div className="px-5 py-2 bg-primary/5 border-t border-primary/10 text-xs text-primary">
              {t("accelerationInvite").replace("{rate}", "5")}
            </div>
          )}
        </div>
      )}

      {/* Context bar */}
      <div className="flex items-center gap-3 text-xs text-text-muted px-1">
        <span className="font-mono font-medium text-text-secondary">{numNodes}</span> {t("sensorsLabel")}
        <span className="text-text-muted/50">|</span>
        <span className="font-mono font-medium text-text-secondary">{rateActual}s</span> rate
        <span className="text-text-muted/50">|</span>
        <span className="font-mono font-medium text-text-secondary">{etlBucket}s</span> ETL
      </div>

      {/* Pareto: latency vs combined RAM% */}
      {(() => {
        const paretoPoints: ParetoPoint[] = [];
        for (const dr of results) {
          const device = devices.find((d) => d.meta.device_id === dr.deviceId);
          if (!device) continue;
          const ramTotalMb = device.meta.ram_total_gb * 1024;
          const stack = device.meta.stack_overhead_mb;
          for (const model of MODELS) {
            const inf = dr.inference[model];
            const tr = dr.training[model];
            if (!inf) continue;
            const infMb = inf.rssPeakMb;
            const trainMb = tr?.rssEstimatedMb ?? 0;
            const combined = stack + infMb + trainMb;
            paretoPoints.push({
              deviceId: dr.deviceId,
              deviceName: device.meta.device_name,
              model,
              numNodes,
              latencyP95Ms: inf.latencyP95Ms,
              latencyP99Ms: inf.latencyP99Ms,
              trainingRssMb: trainMb,
              inferenceRssMb: infMb,
              stackOverheadMb: stack,
              ramTotalMb,
              combinedRamPct: Math.round((combined / ramTotalMb) * 100),
              accelerationFactor: inf.accelerationFactor,
              isRecommended: recommendation?.deviceId === dr.deviceId && recommendation?.model === model,
            });
          }
        }
        if (paretoPoints.length === 0) return null;
        return (
          <div className="bg-surface border border-border rounded-lg p-5 space-y-2">
            <h3 className="text-sm font-semibold text-text">Viabilidad: Latencia vs RAM combinada</h3>
            <p className="text-[11px] text-text-muted">
              Cada punto = (dispositivo, modelo) a {numNodes} sensores. Zona verde = inferencia + training simultaneo viable. Puntos sobre 100% = no cabe en RAM.
            </p>
            <ParetoChart points={paretoPoints} etlBudgetMs={etlBucket * 1000} />
          </div>
        );
      })()}

      {/* Device comparison cards — max 2 per row */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {results.map((dr) => {
          const device = devices.find((d) => d.meta.device_id === dr.deviceId);
          if (!device) return null;

          const isLastOdd = results.indexOf(dr) === results.length - 1 && results.length % 2 === 1;

          return (
            <div key={dr.deviceId} className={`bg-surface border border-border rounded-lg ${isLastOdd ? "xl:col-span-2 xl:max-w-[50%]" : ""}`}>
              {/* Device header */}
              <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold text-text">{device.meta.device_name}</div>
                  <div className="text-[10px] text-text-muted">
                    {device.meta.ram_total_gb}GB · {device.meta.arch}
                    {device.meta.cuda_version ? ` · CUDA ${device.meta.cuda_version}` : ""}
                  </div>
                </div>
                <VerdictBadge verdict={dr.globalVerdict} />
              </div>

              {/* Comparison table */}
              <div>
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="text-text-muted">
                      <th className="text-left py-1.5 pl-4 pr-1 font-medium">Modelo</th>
                      <th className="text-right py-1.5 px-1 font-medium"><Tip text={t("tipP95")}>P95</Tip></th>
                      <th className="text-right py-1.5 px-1 font-medium"><Tip text={t("tipAccel")}>Accel.</Tip></th>
                      <th className="text-right py-1.5 px-1 font-medium"><Tip text={t("tipTrainTime")}>Train</Tip></th>
                      <th className="text-right py-1.5 pl-1 pr-3 font-medium"><Tip text="RAM sistema + inferencia + training simultaneo">RAM</Tip></th>
                    </tr>
                  </thead>
                  <tbody>
                    {MODELS.map((model) => {
                      const inf = dr.inference[model];
                      const tr = dr.training[model];
                      if (!inf) return null;

                      const isRecommended = recommendation?.deviceId === dr.deviceId && recommendation?.model === model;

                      return (
                        <tr
                          key={model}
                          className={`border-t border-border/60 ${isRecommended ? "bg-primary/[0.06]" : ""}`}
                        >
                          <td className="py-1.5 pl-4 pr-1">
                            <div className="flex items-center gap-1">
                              <span className={`font-medium ${isRecommended ? "text-primary" : "text-text"}`}>
                                {MODEL_LABELS[model]}
                              </span>
                              {inf.verdict && <VerdictBadge verdict={inf.verdict} />}
                            </div>
                          </td>
                          <td className="py-1.5 px-1 text-right font-mono text-text">{fmtMs(inf.latencyP95Ms)}</td>
                          <td className="py-1.5 px-1 text-right font-mono font-semibold text-text">
                            {Math.round(inf.accelerationFactor).toLocaleString()}x
                          </td>
                          <td className="py-1.5 px-1 text-right font-mono text-text-secondary">
                            {tr ? fmtTime(tr.timeTotalS) : "—"}
                          </td>
                          {(() => {
                            const stack = device.meta.stack_overhead_mb;
                            const ramTotal = device.meta.ram_total_gb * 1024;
                            const infMb = inf.rssPeakMb;
                            const trainMb = tr?.rssEstimatedMb ?? 0;
                            const combined = stack + infMb + trainMb;
                            const pct = Math.round((combined / ramTotal) * 100);
                            const color = pct > 95 ? "text-not-viable" : pct > 80 ? "text-tight" : "text-excellent";
                            return (
                              <td className="py-1.5 pl-1 pr-3 text-right">
                                <span className={`font-mono text-[10px] ${color}`}>{pct}%</span>
                              </td>
                            );
                          })()}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Data provenance footer */}
              <div className="px-4 py-2 border-t border-border/60 flex items-center gap-2">
                <DataBadge source="measured" />
                <span className="text-[10px] text-text-muted">P95, RAM</span>
                <DataBadge source="calculated" />
                <span className="text-[10px] text-text-muted">Train time, Accel.</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
