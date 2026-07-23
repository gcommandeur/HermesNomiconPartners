"use client";

import { useState } from "react";
import { mutate } from "swr";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/crm/error-banner";
import { apiPost } from "@/lib/api/client";

interface SourcingRunResult {
  found: number;
  created: number;
  skipped_existing: number;
  possible_duplicates: number;
  errors: string[];
}

/** Startet einen manuellen Sourcing-Lauf gegen das amtliche
 * Steuerberaterverzeichnis (kein Cron - bewusst nur per Button, siehe
 * Backend POST /sourcing/run). Eingabe: PLZ oder Orte, komma-/
 * zeilengetrennt. */
export function SourcingRunForm() {
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SourcingRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const areas = input
    .split(/[,;\n]/)
    .map((value) => value.trim())
    .filter(Boolean);

  async function handleRun() {
    if (areas.length === 0 || running) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      // Verlaengertes Timeout: der Lauf ist synchron und macht pro Gebiet
      // einen externen Verzeichnis-Request mit hoeflicher Pause (~2s/Gebiet,
      // max. 20 Gebiete) - das Standard-8s-Timeout von apiPost waere zu knapp.
      const runResult = await apiPost<SourcingRunResult>(
        "/sourcing/run",
        { source_type: "steuerberaterverzeichnis", plz_or_ort: areas },
        120_000,
      );
      setResult(runResult);
      // Leads-Liste sofort aktualisieren (gleicher SWR-Key wie in
      // sourcing-leads-table.tsx).
      await mutate("/sourcing/leads-open");
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Sourcing-Lauf fehlgeschlagen.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mb-6 rounded-lg border border-white/10 bg-[#0D1B2E] p-4">
      <p className="mb-2 text-sm font-semibold text-[#D8DADF]">
        Steuerberaterverzeichnis durchsuchen
      </p>
      <p className="mb-3 text-xs text-[#94A3B8]">
        PLZ oder Orte (kommagetrennt, max. 20) – findet alle dort bestellten
        Steuerberater:innen im amtlichen Verzeichnis der Bundessteuerberaterkammer und legt sie
        als Leads zur Prüfung an.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="z.B. 70173, 80331, Würzburg"
          className="h-9 w-full max-w-md rounded-md border border-white/15 bg-white/5 px-3 text-sm text-[#D8DADF] placeholder:text-[#5b6167] focus:outline-none focus:ring-2 focus:ring-[#1F5FA8]/30"
        />
        <Button size="sm" disabled={areas.length === 0 || areas.length > 20 || running} onClick={() => void handleRun()}>
          <Play size={14} />
          {running ? "Lauf läuft…" : "Lauf starten"}
        </Button>
      </div>
      {areas.length > 20 && (
        <p className="mt-2 text-xs text-[#e4aeb4]">Maximal 20 Gebiete pro Lauf.</p>
      )}
      <ErrorBanner message={error} className="mt-3" />
      {result && (
        <div className="mt-3 rounded-md border border-[#1F5FA8]/30 bg-[#1F5FA8]/10 p-3 text-xs text-[#CBD5E1]">
          {result.found} Treffer im Verzeichnis · {result.created} neue Leads angelegt
          {result.possible_duplicates > 0 && (
            <> (davon {result.possible_duplicates} mögliche Duplikate zu bestehenden Kandidaten)</>
          )}
          {" "}· {result.skipped_existing} bereits als Lead vorhanden
          {result.errors.length > 0 && (
            <ul className="mt-2 list-disc pl-4 text-[#e4aeb4]">
              {result.errors.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
