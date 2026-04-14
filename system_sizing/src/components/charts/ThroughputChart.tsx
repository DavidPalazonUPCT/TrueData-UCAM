import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import type { TrainingResult, ModelId } from "../../lib/types";

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

interface ThroughputChartProps {
  results: Record<ModelId, TrainingResult | null>;
}

export function ThroughputChart({ results }: ThroughputChartProps) {
  const data = (["cognn", "stgnn-gat", "stgnn-topk"] as ModelId[])
    .map((model) => {
      const r = results[model];
      return r ? { name: MODEL_LABELS[model], model, sps: r.throughputSps } : null;
    })
    .filter(Boolean) as Array<{ name: string; model: ModelId; sps: number }>;

  if (data.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <XAxis dataKey="name" tick={{ fill: "#64748B", fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis
          tick={{ fill: "#64748B", fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => `${v}`}
        />
        <Tooltip
          contentStyle={{ backgroundColor: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, fontSize: 12 }}
          formatter={(v: number) => [`${v.toFixed(1)} samples/s`, "Throughput"]}
        />
        <Bar dataKey="sps" radius={[4, 4, 0, 0]} maxBarSize={40}>
          {data.map((entry) => (
            <Cell key={entry.model} fill={MODEL_COLORS[entry.model]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
