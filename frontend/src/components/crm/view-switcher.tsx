"use client";

// NOMICON: Umschalter "Direct | Überlassung | Gesamt" im Kopf. Zeigt nur freigeschaltete Ansichten
// (bei nur einer Ansicht gar nichts) und merkt die Auswahl serverseitig.
import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { mutate } from "swr";
import { selectMyView, VIEW_HOME, VIEW_LABELS, viewForPath, type ViewKey } from "@/lib/api/views";
import { useActiveView } from "@/lib/api/views-hooks";
import { cn } from "@/lib/utils";

const ORDER: ViewKey[] = ["direct", "staffing", "management"];

export function ViewSwitcher({ className }: { className?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const { views, active } = useActiveView();
  const [busy, setBusy] = useState(false);
  if (views.length <= 1) return null;

  async function choose(view: ViewKey) {
    if (view === active || busy) return;
    setBusy(true);
    try {
      const updated = await selectMyView(view);
      await mutate("/me/views", { data: updated, source: "api" }, { revalidate: false });
      // Gehört die aktuelle Seite einer anderen Ansicht, auf die Startseite der neuen wechseln.
      const current = viewForPath(pathname);
      if (current && current !== view) router.push(VIEW_HOME[view]);
    } catch {
      // Auswahl nicht gespeichert: Oberfläche bleibt in der bisherigen Ansicht.
    } finally {
      setBusy(false);
    }
  }

  return (
    <div role="group" aria-label="Ansicht wechseln" className={cn("inline-flex rounded-lg border border-white/15 bg-brand-panel p-0.5", className)}>
      {ORDER.filter((view) => views.includes(view)).map((view) => (
        <button
          key={view}
          type="button"
          onClick={() => void choose(view)}
          aria-pressed={view === active}
          disabled={busy}
          className={cn(
            "min-h-8 rounded-md px-3 text-xs font-medium transition-colors",
            view === active ? "bg-brand-accent text-white" : "text-brand-muted hover:text-brand-text",
          )}
        >
          {VIEW_LABELS[view]}
        </button>
      ))}
    </div>
  );
}
