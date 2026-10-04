import { DatabaseZap } from "lucide-react";

export function DemoNotice({ source, error }: { source: "api" | "demo" | "error"; error?: string }) {
  if (source === "api") return null;
  return (
    <div className={`mb-5 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${source === "error" ? "border-red-400/25 bg-red-950/30 text-red-200" : "border-brand-accent/25 bg-brand-accent-soft/50 text-brand-soft"}`}>
      <DatabaseZap size={14} />
      {source === "error" ? `API-Fehler: ${error ?? "Backend nicht erreichbar"}` : "Expliziter Demo-Modus mit anonymisierten Entwicklungsdaten."}
    </div>
  );
}
