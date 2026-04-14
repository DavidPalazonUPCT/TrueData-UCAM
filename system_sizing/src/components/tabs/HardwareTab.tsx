import type { DeviceData } from "../../lib/types";
import { useI18n } from "../../lib/i18n";

interface HardwareTabProps {
  devices: DeviceData[];
  numNodes: number;
}

export function HardwareTab({ devices }: HardwareTabProps) {
  const { t } = useI18n();

  return (
    <div className="space-y-6">
      <div className="bg-surface border border-border rounded-lg p-5 space-y-5">
        <h3 className="text-sm font-semibold text-text">{t("specs")}</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-text-muted border-b-2 border-border">
                <th className="text-left py-3 pr-4 font-semibold">Device</th>
                <th className="text-left py-3 px-3 font-semibold">Arch</th>
                <th className="text-right py-3 px-3 font-semibold">RAM</th>
                <th className="text-right py-3 px-3 font-semibold">Stack overhead</th>
                <th className="text-left py-3 px-3 font-semibold">GPU</th>
                <th className="text-left py-3 px-3 font-semibold">CUDA</th>
                <th className="text-left py-3 pl-3 font-semibold">{t("benchmarkDate")}</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((d) => (
                <tr key={d.meta.device_id} className="border-b border-border/50">
                  <td className="py-3 pr-4 font-bold text-text">{d.meta.device_name}</td>
                  <td className="py-3 px-3 font-mono text-text-muted">{d.meta.arch}</td>
                  <td className="py-3 px-3 text-right font-mono text-text">{d.meta.ram_total_gb} GB</td>
                  <td className="py-3 px-3 text-right font-mono text-text-muted">{d.meta.stack_overhead_mb.toFixed(0)} MB</td>
                  <td className="py-3 px-3 text-text-muted">{d.meta.gpu_model ?? "—"}</td>
                  <td className="py-3 px-3 text-text-muted">{d.meta.cuda_version ?? "—"}</td>
                  <td className="py-3 pl-3 text-text-muted">{d.meta.benchmark_date.slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
