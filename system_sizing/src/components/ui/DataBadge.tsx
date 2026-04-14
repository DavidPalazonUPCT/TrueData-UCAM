import type { DataSource } from "../../lib/types";
import { useI18n } from "../../lib/i18n";

const STYLES: Record<DataSource, string> = {
  measured: "bg-excellent/10 text-excellent",
  calculated: "bg-primary/10 text-primary",
};

export function DataBadge({ source }: { source: DataSource }) {
  const { t } = useI18n();
  return (
    <span className={`inline-block px-1.5 py-px rounded text-[9px] font-medium ${STYLES[source]}`}>
      {t(source)}
    </span>
  );
}
