interface MemoryBarProps {
  usedMb: number;
  availableMb: number;
  label: string;
}

export function MemoryBar({ usedMb, availableMb, label }: MemoryBarProps) {
  const ratio = availableMb > 0 ? usedMb / availableMb : 0;
  const pct = Math.min(ratio * 100, 100);
  const color = ratio > 0.9 ? "bg-not-viable" : ratio > 0.8 ? "bg-tight" : ratio > 0.5 ? "bg-viable" : "bg-excellent";

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs">
        <span className="text-text-muted">{label}</span>
        <span className="font-mono text-text-secondary">
          {usedMb.toFixed(0)} / {availableMb.toFixed(0)} MB
          <span className="text-text-muted ml-1.5">({(ratio * 100).toFixed(0)}%)</span>
        </span>
      </div>
      <div className="h-1.5 bg-surface-raised rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all duration-300`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
