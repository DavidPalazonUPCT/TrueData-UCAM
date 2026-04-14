import type { DataSource, Verdict } from "../../lib/types";
import { DataBadge } from "./DataBadge";
import { VerdictBadge } from "./VerdictBadge";

interface MetricCardProps {
  label: string;
  value: string;
  source?: DataSource;
  verdict?: Verdict;
  sub?: string;
}

export function MetricCard({ label, value, source, verdict, sub }: MetricCardProps) {
  return (
    <div className="bg-surface-raised rounded-lg px-3 py-2.5">
      <div className="flex items-center justify-between gap-1 mb-1">
        <span className="text-[11px] text-text-muted">{label}</span>
        {source && <DataBadge source={source} />}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-base font-mono font-semibold text-text leading-none">{value}</span>
        {verdict && <VerdictBadge verdict={verdict} />}
      </div>
      {sub && <p className="text-[11px] text-text-muted mt-1">{sub}</p>}
    </div>
  );
}
