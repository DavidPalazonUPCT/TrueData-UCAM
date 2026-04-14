import type { DeviceData, Verdict } from "../../lib/types";

const VERDICT_DOT: Record<Verdict, string> = {
  excellent: "bg-excellent",
  viable: "bg-viable",
  tight: "bg-tight",
  not_viable: "bg-not-viable",
};

interface DeviceSelectorProps {
  devices: DeviceData[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  deviceVerdicts: Record<string, Verdict>;
}

export function DeviceSelector({ devices, selectedIds, onToggle, deviceVerdicts }: DeviceSelectorProps) {
  return (
    <div className="space-y-1">
      {devices.map((d) => {
        const verdict = deviceVerdicts[d.meta.device_id] ?? "viable";
        const isSelected = selectedIds.includes(d.meta.device_id);
        return (
          <label
            key={d.meta.device_id}
            className={`flex items-center gap-2.5 cursor-pointer rounded-md px-2.5 py-2 transition-colors ${
              isSelected ? "bg-surface-raised" : "hover:bg-surface-raised"
            }`}
          >
            <input
              type="checkbox"
              checked={isSelected}
              onChange={() => onToggle(d.meta.device_id)}
              className="accent-primary"
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-text truncate">{d.meta.device_name}</span>
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${VERDICT_DOT[verdict]}`} />
              </div>
              <span className="text-[10px] text-text-muted">
                {d.meta.ram_total_gb}GB · {d.meta.arch}
                {d.meta.cuda_version ? " · CUDA" : ""}
              </span>
            </div>
          </label>
        );
      })}
    </div>
  );
}
