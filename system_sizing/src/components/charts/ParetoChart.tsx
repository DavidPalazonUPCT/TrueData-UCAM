import {
  ScatterChart, Scatter, XAxis, YAxis, Tooltip,
  ReferenceLine, ReferenceArea, ResponsiveContainer, Cell,
} from "recharts";
import type { ModelId } from "../../lib/types";

const MODEL_LABELS: Record<ModelId, string> = {
  cognn: "CoGNN", "stgnn-gat": "STGNN-GAT", "stgnn-topk": "STGNN-TopK",
};

const MODEL_SHAPES: Record<ModelId, "circle" | "diamond" | "triangle"> = {
  cognn: "circle",
  "stgnn-gat": "diamond",
  "stgnn-topk": "triangle",
};

const DEVICE_COLORS: Record<string, string> = {
  "j30-cpu": "#0891B2",
  "j30-cuda": "#7C3AED",
  "rpi5": "#059669",
  "pc-dev": "#D97706",
  "pc-dev-cuda": "#DC2626",
};

const DEVICE_COLOR_FALLBACK = "#64748B";

function deviceColor(deviceId: string): string {
  return DEVICE_COLORS[deviceId] ?? DEVICE_COLOR_FALLBACK;
}

export interface ParetoPoint {
  deviceId: string;
  deviceName: string;
  model: ModelId;
  numNodes: number;
  /** Primary sizing metric (used for X axis + budget zone). */
  latencyP95Ms: number;
  /** Worst-case latency, kept for tooltip display only. */
  latencyP99Ms: number;
  trainingRssMb: number;
  inferenceRssMb: number;
  stackOverheadMb: number;
  ramTotalMb: number;
  combinedRamPct: number;
  accelerationFactor: number;
  isRecommended: boolean;
}

interface ParetoChartProps {
  points: ParetoPoint[];
  etlBudgetMs: number;
}

function shortDevice(name: string): string {
  if (name.includes("Jetson") && name.includes("CPU")) return "J30-CPU";
  if (name.includes("Jetson") && name.includes("CUDA")) return "J30-CUDA";
  if (name.includes("Raspberry")) return "RPi5";
  if (name.includes("PC") && name.includes("CPU")) return "PC-CPU";
  if (name.includes("PC") && name.includes("CUDA")) return "PC-CUDA";
  return name.split("(")[0]?.trim().slice(0, 8) ?? name;
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: ParetoPoint }> }) {
  if (!active || !payload?.[0]) return null;
  const p = payload[0].payload;
  const infMb = p.inferenceRssMb;
  const trainMb = p.trainingRssMb;
  const totalMb = p.stackOverheadMb + infMb + trainMb;

  return (
    <div className="bg-surface border border-border rounded-lg p-3 text-xs space-y-1.5 shadow-lg min-w-[200px]">
      <div className="flex items-center justify-between gap-3">
        <span className="font-bold text-text">{p.deviceName}</span>
        <span className="font-semibold text-text-secondary">{MODEL_LABELS[p.model]}</span>
      </div>
      <div className="border-t border-border pt-1.5 space-y-1">
        <div className="flex justify-between">
          <span className="text-text-muted">Latencia P95</span>
          <span className="font-mono text-text">{p.latencyP95Ms >= 1000 ? `${(p.latencyP95Ms / 1000).toFixed(2)}s` : `${p.latencyP95Ms.toFixed(1)} ms`}</span>
        </div>
        <div className="flex justify-between text-[10px]">
          <span className="text-text-muted">P99 worst</span>
          <span className="font-mono text-text-muted">{p.latencyP99Ms >= 1000 ? `${(p.latencyP99Ms / 1000).toFixed(2)}s` : `${p.latencyP99Ms.toFixed(1)} ms`}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-text-muted">Aceleracion</span>
          <span className="font-mono text-text">{Math.round(p.accelerationFactor).toLocaleString()}x</span>
        </div>
      </div>
      <div className="border-t border-border pt-1.5 space-y-1">
        <div className="flex justify-between text-text-muted">
          <span>Sistema base</span>
          <span className="font-mono">{p.stackOverheadMb.toFixed(0)} MB</span>
        </div>
        <div className="flex justify-between text-text-muted">
          <span>+ Inferencia</span>
          <span className="font-mono">{infMb.toFixed(0)} MB</span>
        </div>
        <div className="flex justify-between text-text-muted">
          <span>+ Training</span>
          <span className="font-mono">{trainMb.toFixed(0)} MB</span>
        </div>
        <div className="flex justify-between font-semibold border-t border-border/60 pt-1">
          <span className="text-text">RAM total</span>
          <span className={`font-mono ${p.combinedRamPct > 95 ? "text-not-viable" : p.combinedRamPct > 80 ? "text-tight" : "text-excellent"}`}>
            {totalMb.toFixed(0)} MB ({p.combinedRamPct}%)
          </span>
        </div>
      </div>
    </div>
  );
}

export function ParetoChart({ points, etlBudgetMs }: ParetoChartProps) {
  if (points.length === 0) return null;

  const latencyLimit = etlBudgetMs * 0.5;

  const allLat = points.map((p) => p.latencyP95Ms).filter((v) => v > 0);
  const xMin = Math.max(0.5, Math.min(...allLat) * 0.4);
  const xMax = Math.max(...allLat, latencyLimit) * 2;
  const yMax = Math.max(...points.map((p) => p.combinedRamPct), 100) * 1.1;

  // Group by model for separate Scatter (each with its own shape)
  const byModel: Partial<Record<ModelId, ParetoPoint[]>> = {};
  for (const p of points) {
    (byModel[p.model] ??= []).push(p);
  }

  // Collect unique devices for legend
  const deviceIds = [...new Set(points.map((p) => p.deviceId))];

  return (
    <div className="space-y-3">
      <ResponsiveContainer width="100%" height={420}>
        <ScatterChart margin={{ top: 20, right: 30, bottom: 44, left: 20 }}>
          {/* Viable zone background */}
          <ReferenceArea
            x1={xMin} x2={latencyLimit}
            y1={0} y2={100}
            fill="#059669" fillOpacity={0.04}
            ifOverflow="hidden"
          />

          <XAxis
            dataKey="latencyP95Ms"
            type="number"
            scale="log"
            domain={[xMin, xMax]}
            tick={{ fill: "#64748B", fontSize: 10 }}
            axisLine={{ stroke: "#E2E8F0" }}
            tickLine={false}
            tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`}
            label={{ value: "Latencia inferencia P95 (log) — menor = mejor", position: "bottom", fill: "#94A3B8", fontSize: 10, offset: 20 }}
          />
          <YAxis
            dataKey="combinedRamPct"
            type="number"
            domain={[0, yMax]}
            tick={{ fill: "#64748B", fontSize: 10 }}
            axisLine={{ stroke: "#E2E8F0" }}
            tickLine={false}
            tickFormatter={(v: number) => `${Math.round(v)}%`}
            label={{ value: "RAM Combinada %", angle: -90, position: "center", fill: "#94A3B8", fontSize: 10, dx: -20 }}
          />

          <Tooltip content={<CustomTooltip />} />

          {/* Hard boundary: 100% RAM */}
          <ReferenceLine
            y={100}
            stroke="#DC2626"
            strokeWidth={2}
            strokeDasharray="8 4"
            label={{ value: "100% RAM — no cabe", fill: "#DC2626", fontSize: 10, position: "insideTopLeft" }}
          />
          {/* Soft boundary: 80% RAM */}
          <ReferenceLine
            y={80}
            stroke="#D97706"
            strokeWidth={1}
            strokeDasharray="4 4"
            label={{ value: "80%", fill: "#D97706", fontSize: 9, position: "insideTopLeft" }}
          />
          {/* Latency budget */}
          <ReferenceLine
            x={latencyLimit}
            stroke="#DC2626"
            strokeWidth={1.5}
            strokeDasharray="6 3"
            label={{ value: "50% ETL budget", fill: "#DC2626", fontSize: 9, position: "insideTopRight" }}
          />

          {/* One Scatter per model → each gets its own shape */}
          {(["cognn", "stgnn-gat", "stgnn-topk"] as ModelId[]).map((model) => {
            const pts = byModel[model];
            if (!pts?.length) return null;
            return (
              <Scatter
                key={model}
                name={MODEL_LABELS[model]}
                data={pts}
                shape={MODEL_SHAPES[model]}
                isAnimationActive={false}
                legendType={MODEL_SHAPES[model]}
              >
                {pts.map((p, i) => (
                  <Cell
                    key={i}
                    fill={deviceColor(p.deviceId)}
                    stroke={p.isRecommended ? "#1E293B" : deviceColor(p.deviceId)}
                    strokeWidth={p.isRecommended ? 3 : 1}
                    r={p.isRecommended ? 10 : 7}
                    opacity={p.combinedRamPct > 100 ? 0.4 : 0.85}
                  />
                ))}
              </Scatter>
            );
          })}
        </ScatterChart>
      </ResponsiveContainer>

      {/* Legend: devices (color) + models (shape) */}
      <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-[11px] px-4">
        {/* Devices */}
        {deviceIds.map((id) => (
          <span key={id} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: deviceColor(id) }} />
            <span className="text-text-muted">{shortDevice(points.find((p) => p.deviceId === id)?.deviceName ?? id)}</span>
          </span>
        ))}
        <span className="text-text-muted/40 mx-1">|</span>
        {/* Models */}
        {(["cognn", "stgnn-gat", "stgnn-topk"] as ModelId[]).map((m) => (
          <span key={m} className="flex items-center gap-1.5">
            <svg width={12} height={12} viewBox="0 0 12 12">
              {MODEL_SHAPES[m] === "circle" && <circle cx={6} cy={6} r={4} fill="#64748B" />}
              {MODEL_SHAPES[m] === "diamond" && <polygon points="6,1 11,6 6,11 1,6" fill="#64748B" />}
              {MODEL_SHAPES[m] === "triangle" && <polygon points="6,1 11,11 1,11" fill="#64748B" />}
            </svg>
            <span className="text-text-muted">{MODEL_LABELS[m]}</span>
          </span>
        ))}
        <span className="text-text-muted/40 mx-1">|</span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full border-2 border-text bg-transparent" />
          <span className="text-text-muted">Recomendado</span>
        </span>
      </div>
    </div>
  );
}
