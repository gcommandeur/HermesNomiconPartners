"use client";

import { RefreshCw, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Wird gezeigt, wenn ein SWR-Hook einen `error` liefert (Backend nicht
 * erreichbar, Request fehlgeschlagen/timeout) - verhindert, dass die Seite
 * bei einem echten Backend-Ausfall dauerhaft im leeren "0 von 0"-Zustand
 * haengen bleibt, ohne dass sichtbar wird, dass ueberhaupt ein Fehler
 * vorliegt. */
export function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-brand-danger/40 bg-brand-danger/10 p-10 text-center" /* NOMICON: lesbar im hellen Theme */>
      <WifiOff size={28} className="text-brand-danger" />
      <p className="text-sm font-semibold text-brand-text">Backend nicht erreichbar</p>
      <p className="max-w-sm text-xs text-brand-muted">
        Die Daten konnten nicht geladen werden. Bitte prüfen, ob das Backend läuft, und erneut versuchen.
      </p>
      <Button size="sm" variant="outline" onClick={onRetry}>
        <RefreshCw size={14} />Erneut versuchen
      </Button>
    </div>
  );
}
