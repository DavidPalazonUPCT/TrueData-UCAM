interface NumericInputProps {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}

export function NumericInput({ label, value, onChange, min = 0, max = 999999, step = 1 }: NumericInputProps) {
  return (
    <div className="space-y-1">
      <label className="text-[11px] text-text-muted font-medium">{label}</label>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full bg-surface-raised border border-border rounded px-2.5 py-1.5 text-sm font-mono text-text focus:border-primary focus:outline-none transition-colors"
      />
    </div>
  );
}
