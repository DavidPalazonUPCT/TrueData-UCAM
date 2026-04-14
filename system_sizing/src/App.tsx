import { useDeviceData } from "./hooks/useDeviceData";
import { useSizingCalc } from "./hooks/useSizingCalc";
import { useI18n } from "./lib/i18n";
import { TopBar } from "./components/layout/TopBar";
import { Sidebar } from "./components/layout/Sidebar";
import { OverviewTab } from "./components/tabs/OverviewTab";
import { InferenceTab } from "./components/tabs/InferenceTab";
import { TrainingTab } from "./components/tabs/TrainingTab";
import { HardwareTab } from "./components/tabs/HardwareTab";
import { MethodologyTab } from "./components/tabs/MethodologyTab";
import { Loader2 } from "lucide-react";

type TabId = "overview" | "inference" | "training" | "hardware" | "methodology";

const TAB_KEYS: TabId[] = ["overview", "inference", "training", "hardware", "methodology"];

export default function App() {
  const { devices, loading, error } = useDeviceData();
  const { t } = useI18n();
  const calc = useSizingCalc(devices);

  if (loading) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <Loader2 size={32} className="text-primary animate-spin" />
      </div>
    );
  }

  if (error || devices.length === 0) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <p className="text-text-muted">{t("noData")}</p>
      </div>
    );
  }

  const tabI18n: Record<TabId, string> = {
    overview: t("overview"),
    inference: t("inference"),
    training: t("training"),
    hardware: t("hardware"),
    methodology: t("methodology"),
  };

  return (
    <div className="h-screen bg-bg text-text font-sans flex flex-col overflow-hidden">
      <TopBar />
      <div className="flex flex-1 min-h-0">
        <Sidebar
          measuredNodes={calc.measuredNodes}
          numNodes={calc.numNodes}
          onNumNodesChange={calc.setNumNodes}
          rateActual={calc.rateActual}
          onRateChange={calc.setRateActual}
          etlBucket={calc.etlBucket}
          onBucketChange={calc.setEtlBucket}
          datasetSize={calc.datasetSize}
          onDatasetChange={calc.setDatasetSize}
          epochs={calc.epochs}
          onEpochsChange={calc.setEpochs}
          devices={devices}
          selectedDeviceIds={calc.selectedDeviceIds}
          onToggleDevice={calc.toggleDevice}
          deviceVerdicts={calc.deviceVerdicts}
        />

        <main className="flex-1 overflow-y-auto">
          {/* Tab bar */}
          <div className="border-b border-border bg-surface sticky top-0 z-10">
            <div className="flex px-6 gap-1">
              {TAB_KEYS.map((tab) => (
                <button
                  key={tab}
                  onClick={() => calc.setActiveTab(tab)}
                  className={`px-3.5 py-3 text-xs font-medium border-b-2 transition-colors cursor-pointer ${
                    calc.activeTab === tab
                      ? "border-primary text-primary"
                      : "border-transparent text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {tabI18n[tab]}
                </button>
              ))}
            </div>
          </div>

          {/* Tab content */}
          <div className="p-6">
            {calc.activeTab === "overview" && (
              <OverviewTab
                results={calc.results}
                devices={calc.selectedDevices}
                rateActual={calc.rateActual}
                numNodes={calc.numNodes}
                etlBucket={calc.etlBucket}
                recommendation={calc.recommendation}
              />
            )}
            {calc.activeTab === "inference" && (
              <InferenceTab
                results={calc.results}
                devices={calc.selectedDevices}
                numNodes={calc.numNodes}
                etlBucket={calc.etlBucket}
                rateActual={calc.rateActual}
              />
            )}
            {calc.activeTab === "training" && (
              <TrainingTab
                results={calc.results}
                devices={calc.selectedDevices}
                numNodes={calc.numNodes}
                datasetSize={calc.datasetSize}
                epochs={calc.epochs}
              />
            )}
            {calc.activeTab === "hardware" && (
              <HardwareTab
                devices={calc.selectedDevices}
                numNodes={calc.numNodes}
              />
            )}
            {calc.activeTab === "methodology" && <MethodologyTab />}
          </div>
        </main>
      </div>
    </div>
  );
}
