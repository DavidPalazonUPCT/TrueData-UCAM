import { BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer, Cell } from "recharts";
import type { InferenceResult, ModelId } from "../../lib/types";

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

interface LatencyBarChartProps {
  results: Record<ModelId, InferenceResult | null>;
  etlBudgetMs: number;
}

export function LatencyBarChart({ results, etlBudgetMs }: LatencyBarChartProps) {
  const data = (["cognn", "stgnn-gat", "stgnn-topk"] as ModelId[])
    .map((model) => {
      const r = results[model];
      return r ? { name: MODEL_LABELS[model], model, p95: r.latencyP95Ms } : null;
    })
    .filter(Boolean) as Array<{ name: string; model: ModelId; p95: number }>;

  if (data.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <XAxis dataKey="name" tick={{ fill: "#64748B", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis
          tick={{ fill: "#64748B", fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}ms`}
        />
        <Tooltip
          contentStyle={{ backgroundColor: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, fontSize: 12 }}
          formatter={(v: number) => [`${v.toFixed(1)} ms`, "P95 Latency"]}
        />
        <ReferenceLine
          y={etlBudgetMs * 0.5}
          stroke="#F87171"
          strokeDasharray="4 4"
          label={{ value: "50% budget", fill: "#F87171", fontSize: 10, position: "right" }}
        />
        <Bar dataKey="p95" radius={[4, 4, 0, 0]} maxBarSize={40}>
          {data.map((entry) => (
            <Cell key={entry.model} fill={MODEL_COLORS[entry.model]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
