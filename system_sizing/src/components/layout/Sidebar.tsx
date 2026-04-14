import type { DeviceData, Verdict } from "../../lib/types";
import { useI18n } from "../../lib/i18n";
import { DiscreteSlider } from "../controls/DiscreteSlider";
import { NumericInput } from "../controls/NumericInput";
import { DeviceSelector } from "../controls/DeviceSelector";

interface SidebarProps {
  measuredNodes: number[];
  numNodes: number;
  onNumNodesChange: (v: number) => void;
  rateActual: number;
  onRateChange: (v: number) => void;
  etlBucket: number;
  onBucketChange: (v: number) => void;
  datasetSize: number;
  onDatasetChange: (v: number) => void;
  epochs: number;
  onEpochsChange: (v: number) => void;
  devices: DeviceData[];
  selectedDeviceIds: string[];
  onToggleDevice: (id: string) => void;
  deviceVerdicts: Record<string, Verdict>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="px-4 py-4 border-b border-border">
      <div className="text-[10px] font-semibold text-text-muted uppercase tracking-widest mb-3">{title}</div>
      {children}
    </div>
  );
}

export function Sidebar({
  measuredNodes, numNodes, onNumNodesChange,
  rateActual, onRateChange,
  etlBucket, onBucketChange,
  datasetSize, onDatasetChange,
  epochs, onEpochsChange,
  devices, selectedDeviceIds, onToggleDevice,
  deviceVerdicts,
}: SidebarProps) {
  const { t } = useI18n();

  return (
    <aside className="w-64 bg-surface border-r border-border overflow-y-auto shrink-0">
      {/* Plant configuration */}
      <Section title={t("plantConfig")}>
        <div className="space-y-3">
          <DiscreteSlider
            label={t("sensors")}
            values={measuredNodes}
            value={numNodes}
            onChange={onNumNodesChange}
          />
          <NumericInput label={t("currentRate")} value={rateActual} onChange={onRateChange} min={1} max={60} />
          <p className="text-[10px] text-primary italic -mt-1">{t("sampleFaster")}</p>
        </div>
      </Section>

      {/* Operational config */}
      <Section title={t("trainingProjection")}>
        <div className="space-y-3">
          <NumericInput label={t("etlBucket")} value={etlBucket} onChange={onBucketChange} min={1} max={60} />
          <NumericInput label={t("datasetSize")} value={datasetSize} onChange={onDatasetChange} min={100} max={100000} step={1000} />
          <NumericInput label={t("epochs")} value={epochs} onChange={onEpochsChange} min={1} max={100} />
        </div>
      </Section>

      {/* Devices */}
      <Section title={t("devices")}>
        <DeviceSelector
          devices={devices}
          selectedIds={selectedDeviceIds}
          onToggle={onToggleDevice}
          deviceVerdicts={deviceVerdicts}
        />
      </Section>
    </aside>
  );
}
