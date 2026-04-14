import {
  ComposedChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  ReferenceLine, ResponsiveContainer,
} from "recharts";
import type { ModelId, InferenceBenchmark } from "../../lib/types";

const MODEL_LABELS: Record<ModelId, string> = {
  cognn: "CoGNN",
  "stgnn-gat": "STGNN-GAT",
  "stgnn-topk": "STGNN-TopK",
};

const MODEL_COLORS: Record<ModelId, string> = {
  cognn: "#F87171",
  "stgnn-gat": "#FBBF24",
  "stgnn-topk": "#34D399",
};

const X_TICKS = [20, 50, 100, 200, 500];

interface LatencyCurveChartProps {
  benchmarks: InferenceBenchmark[];
  etlBudgetMs: number;
  currentNodes: number;
}

interface RowData {
  num_nodes: number;
  [key: string]: number | undefined;
}

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ dataKey: string; value: number; color: string }>; label?: number }) {
  if (!active || !payload?.length) return null;

  const formatMs = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(2)}s` : `${v.toFixed(1)}ms`);

  const byModel = new Map<ModelId, { p50?: number; p95?: number; p99?: number }>();
  for (const p of payload) {
    if (typeof p.value !== "number") continue;
    const match = p.dataKey.match(/^(cognn|stgnn-gat|stgnn-topk)_(p50|p95|p99)$/);
    if (!match) continue;
    const [, model, field] = match;
    if (!model || !field) continue;
    const m = model as ModelId;
    if (!byModel.has(m)) byModel.set(m, {});
    (byModel.get(m) as Record<string, number>)[field] = p.value;
  }
  if (byModel.size === 0) return null;

  return (
    <div className="bg-surface border border-border rounded-lg p-2.5 text-xs shadow-lg space-y-2">
      <p className="text-text-muted font-mono">{label} sensores</p>
      {[...byModel.entries()].map(([model, fields]) => (
        <div key={model} className="space-y-0.5">
          <div className="flex items-baseline gap-2">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: MODEL_COLORS[model] }} />
            <span className="font-semibold text-text">{MODEL_LABELS[model]}</span>
          </div>
          {fields.p50 != null && (
            <div className="pl-4 text-[10px] text-text-muted font-mono">
              P50: {formatMs(fields.p50)}
            </div>
          )}
          {fields.p95 != null && (
            <div className="pl-4 text-[10px] text-text-muted font-mono">
              P95: {formatMs(fields.p95)}
            </div>
          )}
          {fields.p99 != null && (
            <div className="pl-4 text-[10px] text-text-muted font-mono">
              P99: {formatMs(fields.p99)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export function LatencyCurveChart({ benchmarks, etlBudgetMs, currentNodes }: LatencyCurveChartProps) {
  if (benchmarks.length === 0) return null;

  const allNodes = new Set<number>();
  for (const b of benchmarks) allNodes.add(b.num_nodes);
  const sortedNodes = [...allNodes].sort((a, b) => a - b);

  const data: RowData[] = sortedNodes.map((n) => {
    const row: RowData = { num_nodes: n };
    for (const b of benchmarks) {
      if (b.num_nodes !== n) continue;
      row[`${b.model}_p50`] = b.latency.p50_ms;
      row[`${b.model}_p95`] = b.latency.p95_ms;
      row[`${b.model}_p99`] = b.latency.p99_ms;
    }
    return row;
  });

  const models: ModelId[] = ["cognn", "stgnn-gat", "stgnn-topk"];

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 4 }}>
        <CartesianGrid
          vertical
          horizontal={false}
          stroke="#334155"
          strokeOpacity={0.25}
          strokeDasharray="2 4"
        />
        <XAxis
          dataKey="num_nodes"
          scale="linear"
          type="number"
          domain={[0, 500]}
          ticks={X_TICKS}
          tick={{ fill: "#64748B", fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          interval={0}
        />
        <YAxis
          scale="log"
          domain={["auto", "auto"]}
          tick={{ fill: "#64748B", fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          width={48}
          tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`}
        />
        <Tooltip content={<CustomTooltip />} />

        {/* ETL budget line at 50% of the window */}
        <ReferenceLine
          y={etlBudgetMs * 0.5}
          stroke="#F87171"
          strokeDasharray="6 3"
          strokeOpacity={0.6}
        />

        {/* Current number-of-sensors indicator */}
        <ReferenceLine
          x={currentNodes}
          stroke="#06B6D4"
          strokeDasharray="4 4"
          strokeOpacity={0.4}
        />

        {/* P95 dashed line — informative */}
        {models.map((m) => (
          <Line
            key={`${m}_p95`}
            type="monotone"
            dataKey={`${m}_p95`}
            stroke={MODEL_COLORS[m]}
            strokeWidth={1}
            strokeDasharray="3 3"
            strokeOpacity={0.6}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        ))}

        {/* P50 main line with dots at measured points */}
        {models.map((m) => (
          <Line
            key={`${m}_p50`}
            type="monotone"
            dataKey={`${m}_p50`}
            stroke={MODEL_COLORS[m]}
            strokeWidth={2}
            dot={{ fill: MODEL_COLORS[m], r: 4, strokeWidth: 2, stroke: "#0B1222" }}
            connectNulls
            isAnimationActive={false}
          />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
