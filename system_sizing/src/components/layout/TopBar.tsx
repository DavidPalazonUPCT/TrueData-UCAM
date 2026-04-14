import { useI18n } from "../../lib/i18n";
import { Activity } from "lucide-react";

export function TopBar() {
  const { lang, t, setLang } = useI18n();

  return (
    <header className="h-14 bg-surface border-b border-border flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-2.5">
        <Activity size={18} className="text-primary" />
        <div>
          <h1 className="text-sm font-semibold text-text leading-tight">{t("title")}</h1>
          <p className="text-[11px] text-text-muted">{t("subtitle")}</p>
        </div>
      </div>
      <button
        onClick={() => setLang(lang === "es" ? "en" : "es")}
        className="px-2.5 py-1 text-xs font-medium border border-border rounded-md hover:border-primary hover:text-primary transition-colors text-text-muted cursor-pointer"
      >
        {lang === "es" ? "EN" : "ES"}
      </button>
    </header>
  );
}
