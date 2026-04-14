import type { SizingParams } from "./types";

const DEFAULTS: SizingParams = {
  numNodes: 100,
  rateActualSeconds: 1,
  etlBucketSeconds: 5,
  datasetSize: 1700,
  epochs: 20,
  selectedDeviceIds: [],
  activeTab: "overview",
  lang: "es",
};

export function readUrlState(): Partial<SizingParams> {
  const params = new URLSearchParams(window.location.search);
  const result: Partial<SizingParams> = {};

  const nodes = params.get("nodes");
  if (nodes) result.numNodes = Number(nodes);

  const rate = params.get("rate");
  if (rate) result.rateActualSeconds = Number(rate);

  const bucket = params.get("bucket");
  if (bucket) result.etlBucketSeconds = Number(bucket);

  const dataset = params.get("dataset");
  if (dataset) result.datasetSize = Number(dataset);

  const epochs = params.get("epochs");
  if (epochs) result.epochs = Number(epochs);

  const devices = params.get("devices");
  if (devices) result.selectedDeviceIds = devices.split(",");

  const tab = params.get("tab");
  if (tab) result.activeTab = tab;

  const lang = params.get("lang");
  if (lang === "es" || lang === "en") result.lang = lang;

  return result;
}

export function writeUrlState(state: SizingParams) {
  const params = new URLSearchParams();
  if (state.numNodes !== DEFAULTS.numNodes) params.set("nodes", String(state.numNodes));
  if (state.rateActualSeconds !== DEFAULTS.rateActualSeconds) params.set("rate", String(state.rateActualSeconds));
  if (state.etlBucketSeconds !== DEFAULTS.etlBucketSeconds) params.set("bucket", String(state.etlBucketSeconds));
  if (state.datasetSize !== DEFAULTS.datasetSize) params.set("dataset", String(state.datasetSize));
  if (state.epochs !== DEFAULTS.epochs) params.set("epochs", String(state.epochs));
  if (state.selectedDeviceIds.length > 0) params.set("devices", state.selectedDeviceIds.join(","));
  if (state.activeTab !== DEFAULTS.activeTab) params.set("tab", state.activeTab);
  if (state.lang !== DEFAULTS.lang) params.set("lang", state.lang);

  const search = params.toString();
  const url = search ? `?${search}` : window.location.pathname;
  window.history.replaceState(null, "", url);
}

export { DEFAULTS };
