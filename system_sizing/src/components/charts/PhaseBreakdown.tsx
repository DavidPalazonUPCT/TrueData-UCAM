interface Phase {
  name: string;
  pct: number;
  color: string;
}

interface PhaseBreakdownProps {
  phases: Phase[];
}

export function PhaseBreakdown({ phases }: PhaseBreakdownProps) {
  return (
    <div className="space-y-1">
      <div className="h-3 rounded-full overflow-hidden flex">
        {phases.map((p) => (
          <div
            key={p.name}
            className="h-full transition-all duration-300"
            style={{ width: `${p.pct}%`, backgroundColor: p.color }}
            title={`${p.name}: ${p.pct.toFixed(1)}%`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {phases.map((p) => (
          <span key={p.name} className="flex items-center gap-1 text-[10px] text-text-muted">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
            {p.name} {p.pct.toFixed(1)}%
          </span>
        ))}
      </div>
    </div>
  );
}
