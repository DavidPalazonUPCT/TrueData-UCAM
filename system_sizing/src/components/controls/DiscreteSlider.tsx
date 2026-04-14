interface DiscreteSliderProps {
  label: string;
  values: number[];
  value: number;
  onChange: (v: number) => void;
}

export function DiscreteSlider({ label, values, value, onChange }: DiscreteSliderProps) {
  const idx = values.indexOf(value);
  const currentIdx = idx >= 0 ? idx : 0;

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between items-baseline">
        <span className="text-[11px] text-text-muted font-medium">{label}</span>
        <span className="text-sm font-mono font-semibold text-text">{value}</span>
      </div>
      <input
        type="range"
        min={0}
        max={values.length - 1}
        step={1}
        value={currentIdx}
        onChange={(e) => {
          const v = values[Number(e.target.value)];
          if (v !== undefined) onChange(v);
        }}
        className="w-full accent-primary"
      />
      <div className="flex justify-between text-[9px] text-text-muted">
        {values.map((v) => (
          <span key={v}>{v}</span>
        ))}
      </div>
    </div>
  );
}
