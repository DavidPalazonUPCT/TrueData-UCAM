import { useState, useEffect } from "react";
import type { DeviceData } from "../lib/types";
import { deviceDataSchema } from "../lib/schema";

const DEVICE_FILES = ["beelink.json", "rpi5.json", "j30-cpu.json", "j30-cuda.json", "pc-dev.json", "pc-dev-cuda.json"];

export function useDeviceData() {
  const [devices, setDevices] = useState<DeviceData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const results: DeviceData[] = [];
      const errors: string[] = [];

      const deviceFetches = DEVICE_FILES.map(async (file) => {
        try {
          const res = await fetch(`${import.meta.env.BASE_URL}data/${file}`);
          if (!res.ok) return;
          const json: unknown = await res.json();
          const parsed = deviceDataSchema.safeParse(json);
          if (parsed.success) {
            results.push(parsed.data as DeviceData);
          } else {
            errors.push(`${file}: validation failed`);
          }
        } catch {
          // Device file not available — skip silently
        }
      });

      await Promise.all(deviceFetches);

      if (!cancelled) {
        setDevices(results);
        setError(errors.length > 0 ? errors.join("; ") : null);
        setLoading(false);
      }
    }

    void load();
    return () => { cancelled = true; };
  }, []);

  return { devices, loading, error };
}
