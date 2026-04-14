import { useState, useMemo, useCallback, useEffect } from "react";
import type { DeviceData, ModelId, InferenceResult, TrainingResult, Verdict, SizingParams } from "../lib/types";
import {
  calcRamAvailable,
  calcInferenceResult,
  calcTrainingResult,
  findInferenceBenchmark,
  findTrainingByBatchSize,
  findClosestTrainingMemory,
  bestOption,
  REFERENCE_BATCH_SIZE,
} from "../lib/calculations";
import { readUrlState, writeUrlState, DEFAULTS } from "../lib/url-state";
import { setLang } from "../lib/i18n";

const MODELS: ModelId[] = ["cognn", "stgnn-gat", "stgnn-topk"];

export interface DeviceResults {
  deviceId: string;
  inference: Record<ModelId, InferenceResult | null>;
  training: Record<ModelId, TrainingResult | null>;
  globalVerdict: Verdict;
}

export function useSizingCalc(devices: DeviceData[]) {
  const urlState = useMemo(() => readUrlState(), []);

  const [numNodes, setNumNodes] = useState(urlState.numNodes ?? DEFAULTS.numNodes);
  const [rateActual, setRateActual] = useState(urlState.rateActualSeconds ?? DEFAULTS.rateActualSeconds);
  const [etlBucket, setEtlBucket] = useState(urlState.etlBucketSeconds ?? DEFAULTS.etlBucketSeconds);
  const [datasetSize, setDatasetSize] = useState(urlState.datasetSize ?? DEFAULTS.datasetSize);
  const [epochs, setEpochs] = useState(urlState.epochs ?? DEFAULTS.epochs);
  const [activeTab, setActiveTab] = useState(urlState.activeTab ?? DEFAULTS.activeTab);
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<string[]>(
    urlState.selectedDeviceIds?.length ? urlState.selectedDeviceIds : devices.map((d) => d.meta.device_id),
  );

  useEffect(() => {
    if (urlState.lang) setLang(urlState.lang);
  }, [urlState.lang]);

  useEffect(() => {
    if (devices.length > 0 && selectedDeviceIds.length === 0) {
      setSelectedDeviceIds(devices.map((d) => d.meta.device_id));
    }
  }, [devices, selectedDeviceIds.length]);

  const measuredNodes = useMemo(() => {
    const all = new Set<number>();
    for (const d of devices) {
      for (const n of d.meta.measured_node_counts) all.add(n);
    }
    return [...all].sort((a, b) => a - b);
  }, [devices]);

  const selectedDevices = useMemo(
    () => devices.filter((d) => selectedDeviceIds.includes(d.meta.device_id)),
    [devices, selectedDeviceIds],
  );

  const results = useMemo<DeviceResults[]>(() => {
    return selectedDevices.map((device) => {
      const ramAvail = calcRamAvailable(device.meta.ram_total_gb, device.meta.stack_overhead_mb);

      const inference = {} as Record<ModelId, InferenceResult | null>;
      const training = {} as Record<ModelId, TrainingResult | null>;
      let worstVerdict: Verdict = "excellent";

      for (const model of MODELS) {
        const inf = findInferenceBenchmark(device, model, numNodes);
        inference[model] = inf
          ? calcInferenceResult(inf, ramAvail, etlBucket, numNodes, rateActual)
          : null;

        const batchSize = REFERENCE_BATCH_SIZE;
        const rec = findTrainingByBatchSize(device, model, numNodes, batchSize);
        if (rec) {
          const memBench = findClosestTrainingMemory(device, model, numNodes, batchSize, datasetSize);
          training[model] = calcTrainingResult(rec, memBench, ramAvail, datasetSize, epochs);
        } else {
          training[model] = null;
        }

        const iv = inference[model]?.verdict;
        const tv = training[model]?.verdict;
        for (const v of [iv, tv]) {
          if (v === "not_viable") worstVerdict = "not_viable";
          else if (v === "tight" && worstVerdict !== "not_viable") worstVerdict = "tight";
          else if (v === "viable" && worstVerdict === "excellent") worstVerdict = "viable";
        }
      }

      return { deviceId: device.meta.device_id, inference, training, globalVerdict: worstVerdict };
    });
  }, [selectedDevices, numNodes, rateActual, etlBucket, datasetSize, epochs]);

  const recommendation = useMemo(() => {
    const best = bestOption(selectedDevices, numNodes, etlBucket, rateActual, datasetSize, epochs);
    if (!best) return null;

    const device = selectedDevices.find((d) => d.meta.device_id === best.deviceId);
    const inf = device ? findInferenceBenchmark(device, best.model, numNodes) : null;
    const accelerationFactor = inf
      ? inf.datapoints_per_sec / (numNodes / rateActual)
      : 0;

    return { ...best, accelerationFactor };
  }, [selectedDevices, numNodes, etlBucket, rateActual, datasetSize, epochs]);

  const deviceVerdicts = useMemo(() => {
    const map: Record<string, Verdict> = {};
    for (const r of results) map[r.deviceId] = r.globalVerdict;
    return map;
  }, [results]);

  const toggleDevice = useCallback((id: string) => {
    setSelectedDeviceIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }, []);

  useEffect(() => {
    const state: SizingParams = {
      numNodes, rateActualSeconds: rateActual, etlBucketSeconds: etlBucket,
      datasetSize, epochs, selectedDeviceIds, activeTab, lang: "es",
    };
    writeUrlState(state);
  }, [numNodes, rateActual, etlBucket, datasetSize, epochs, selectedDeviceIds, activeTab]);

  return {
    numNodes, setNumNodes,
    rateActual, setRateActual,
    etlBucket, setEtlBucket,
    datasetSize, setDatasetSize,
    epochs, setEpochs,
    activeTab, setActiveTab,
    selectedDeviceIds, toggleDevice,
    measuredNodes,
    selectedDevices,
    results,
    recommendation,
    deviceVerdicts,
  };
}
