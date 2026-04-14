import type { Verdict } from "../../lib/types";
import { useI18n } from "../../lib/i18n";
import { Check, AlertTriangle, X } from "lucide-react";

const CONFIG: Record<Verdict, { bg: string; text: string; icon: typeof Check }> = {
  excellent: { bg: "bg-excellent/10", text: "text-excellent", icon: Check },
  viable: { bg: "bg-viable/10", text: "text-viable", icon: Check },
  tight: { bg: "bg-tight/10", text: "text-tight", icon: AlertTriangle },
  not_viable: { bg: "bg-not-viable/10", text: "text-not-viable", icon: X },
};

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const { t } = useI18n();
  const c = CONFIG[verdict];
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold ${c.bg} ${c.text}`}>
      <Icon size={11} />
      {t(verdict)}
    </span>
  );
}
