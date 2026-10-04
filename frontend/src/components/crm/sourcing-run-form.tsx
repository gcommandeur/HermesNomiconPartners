"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import { Play, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/crm/error-banner";
import { apiPost } from "@/lib/api/client";
import { getSourcingRunStatus } from "@/lib/api/queries";
import type { DataResult, SourcingRunStatus } from "@/lib/api/types";

interface SourcingRunResult {
  found: number;
  created: number;
  skipped_existing: number;
  possible_duplicates: number;
  errors: string[];
  background_started: number;
  run_id: string | null;
}

type RunSource = "steuerberaterverzeichnis" | "wpk_berufsregister" | "kanzlei_team_page";

const SOURCE_OPTIONS: { value: RunSource; label: string; hint: string }[] = [
  {
    value: "steuerberaterverzeichnis",
    label: "Steuerberaterverzeichnis",
    hint:
      "PLZ oder Orte (kommagetrennt, max. 20) – oder eine PLZ/ein Ort plus Umkreis. Findet alle " +
      "dort bestellten Steuerberater:innen im amtlichen Verzeichnis der Bundessteuerberaterkammer.",
  },
  {
    value: "wpk_berufsregister",
    label: "WPK-Berufsregister",
    hint:
      "PLZ oder Orte (kommagetrennt, max. 20) – oder eine PLZ/ein Ort plus Umkreis. Findet " +
      "Wirtschaftsprüfer:innen und vereidigte Buchprüfer:innen im Berufsregister der WPK.",
  },
  {
    value: "kanzlei_team_page",
    label: "Kanzlei-Team-Seiten",
    hint:
      "Durchsucht die Websites der im CRM erfassten Kanzleien nach Team-/Mitarbeiter-Seiten und " +
      "extrahiert die dort genannten Personen (KI-Extraktion) – ohne Umkreis alle Kanzleien, mit " +
      "Umkreis nur die Kanzleien rund um die PLZ/den Ort.",
  },
];

// Max. 50 km: die Verzeichnisse kennen nur exakte PLZ, 50 km sind bereits
// bis ~400 Einzelanfragen (~15 min im Hintergrund).
const RADIUS_OPTIONS = ["10", "25", "50"];

/** Startet einen manuellen Sourcing-Lauf (kein Cron - bewusst nur per
 * Button, siehe Backend POST /sourcing/run). */
export function SourcingRunForm() {
  const [source, setSource] = useState<RunSource>("steuerberaterverzeichnis");
  const [input, setInput] = useState("");
  const [radiusKm, setRadiusKm] = useState("");
  const [running, setRunning] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [result, setResult] = useState<SourcingRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Pollt den Hintergrund-Lauf ("alle Kanzleien scannen") alle 4s, solange
  // er laeuft - das ist der einzige Sourcing-Pfad, der lange genug laeuft,
  // um eine Fortschrittsanzeige + Stop-Button zu brauchen (siehe Backend
  // GET /sourcing/status). Stoppt automatisch, sobald der Lauf beendet ist.
  const { data: statusData, mutate: mutateStatus } = useSWR<DataResult<SourcingRunStatus | null>>(
    "/sourcing/status",
    getSourcingRunStatus,
    { refreshInterval: (latest) => (latest?.data?.status === "running" ? 4000 : 0) },
  );
  const activeRun = statusData?.data?.status === "running" ? statusData.data : null;

  const isTeamScrape = source === "kanzlei_team_page";
  const isRadius = radiusKm !== "";
  const areas = input
    .split(/[,;\n]/)
    .map((value) => value.trim())
    .filter(Boolean);
  const inputValid = isRadius
    ? areas.length === 1
    : isTeamScrape || (areas.length > 0 && areas.length <= 20);
  const canRun = !running && !activeRun && inputValid;
  const selectedOption = SOURCE_OPTIONS.find((option) => option.value === source);
  const runUnit = activeRun?.source_type === "kanzlei_team_page" ? "Kanzleien" : "PLZ";

  async function handleStop() {
    setStopping(true);
    setError(null);
    try {
      await apiPost("/sourcing/stop", {});
      await mutateStatus();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Stopp fehlgeschlagen.");
    } finally {
      setStopping(false);
    }
  }

  async function handleRun() {
    if (!canRun) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const body = isRadius
        ? { source_type: source, center: areas[0], radius_km: Number(radiusKm) }
        : isTeamScrape
          ? { source_type: source, scan_all_companies: true }
          : { source_type: source, plz_or_ort: areas };
      // Verlaengertes Timeout: der Verzeichnis-Lauf ohne Umkreis ist synchron
      // und macht pro Gebiet einen externen Request mit hoeflicher Pause
      // (~2s/Gebiet, max. 20 Gebiete) - das Standard-8s-Timeout von apiPost
      // waere zu knapp. Umkreissuche und Team-Scan antworten dagegen sofort
      // (Background-Task).
      const runResult = await apiPost<SourcingRunResult>("/sourcing/run", body, 120_000);
      setResult(runResult);
      // Leads-Liste sofort aktualisieren (gleicher SWR-Key wie in
      // sourcing-leads-table.tsx).
      await mutate("/sourcing/leads-open");
      if (runResult.run_id) await mutateStatus();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Sourcing-Lauf fehlgeschlagen.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mb-6 rounded-lg border border-white/10 bg-brand-surface p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold text-brand-platinum">Sourcing-Lauf starten</p>
        {activeRun && (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-accent/40 bg-brand-accent/15 px-2.5 py-0.5 text-[11px] font-medium text-[#8FB4E3]">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#8FB4E3]" />
            Läuft: {activeRun.processed}/{activeRun.total} {runUnit}
            {activeRun.leads_created > 0 && ` · ${activeRun.leads_created} neue Leads`}
            {activeRun.stop_requested && " · wird gestoppt…"}
          </span>
        )}
      </div>
      <p className="mb-3 text-xs text-brand-muted">{selectedOption?.hint}</p>
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={source}
          disabled={!!activeRun}
          onChange={(event) => {
            setSource(event.target.value as RunSource);
            setResult(null);
            setError(null);
          }}
          className="h-9 rounded-md border border-white/15 bg-brand-surface px-2 text-sm text-brand-platinum focus:outline-none focus:ring-2 focus:ring-brand-accent/30 disabled:opacity-50"
        >
          {SOURCE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {(!isTeamScrape || isRadius) && (
          <input
            value={input}
            disabled={!!activeRun}
            onChange={(event) => setInput(event.target.value)}
            placeholder={isRadius ? "PLZ oder Ort, z.B. 70191" : "z.B. 70173, 80331, Würzburg"}
            className="h-9 w-full max-w-md rounded-md border border-white/15 bg-white/5 px-3 text-sm text-brand-platinum placeholder:text-brand-gray-dark focus:outline-none focus:ring-2 focus:ring-brand-accent/30 disabled:opacity-50"
          />
        )}
        <select
          value={radiusKm}
          disabled={!!activeRun}
          onChange={(event) => {
            setRadiusKm(event.target.value);
            setResult(null);
            setError(null);
          }}
          className="h-9 rounded-md border border-white/15 bg-brand-surface px-2 text-sm text-brand-platinum focus:outline-none focus:ring-2 focus:ring-brand-accent/30 disabled:opacity-50"
        >
          <option value="">{isTeamScrape ? "Alle Kanzleien" : "Kein Umkreis"}</option>
          {RADIUS_OPTIONS.map((km) => (
            <option key={km} value={km}>
              Umkreis {km} km
            </option>
          ))}
        </select>
        {activeRun ? (
          <Button
            size="sm"
            variant="outline"
            disabled={stopping || activeRun.stop_requested}
            onClick={() => void handleStop()}
          >
            <Square size={14} />
            {activeRun.stop_requested ? "Stopp angefordert…" : stopping ? "Stoppe…" : "Stoppen"}
          </Button>
        ) : (
          <Button size="sm" disabled={!canRun} onClick={() => void handleRun()}>
            <Play size={14} />
            {running
              ? "Lauf läuft…"
              : isRadius
                ? "Umkreissuche starten"
                : isTeamScrape
                  ? "Alle Kanzleien scannen"
                  : "Lauf starten"}
          </Button>
        )}
      </div>
      {!isRadius && areas.length > 20 && !isTeamScrape && (
        <p className="mt-2 text-xs text-brand-danger-soft">Maximal 20 Gebiete pro Lauf.</p>
      )}
      {isRadius && areas.length > 1 && (
        <p className="mt-2 text-xs text-brand-danger-soft">Für die Umkreissuche genau eine PLZ oder einen Ort angeben.</p>
      )}
      <ErrorBanner message={error} className="mt-3" />
      {result && (
        <div className="mt-3 rounded-md border border-brand-accent/30 bg-brand-accent/10 p-3 text-xs text-brand-soft">
          {result.background_started > 0 ? (
            <>
              {isTeamScrape
                ? `Team-Scan für ${result.background_started} Kanzleien mit Website`
                : `Umkreissuche über ${result.background_started} PLZ`}{" "}
              im Hintergrund gestartet – gefundene Leads erscheinen nach und nach in der Liste
              unten (Seite später neu laden).
            </>
          ) : (
            <>
              {result.found} Treffer in der Quelle · {result.created} neue Leads angelegt
              {result.possible_duplicates > 0 && (
                <>
                  {" "}
                  (davon {result.possible_duplicates} mögliche Duplikate zu bestehenden Kandidaten)
                </>
              )}{" "}
              · {result.skipped_existing} bereits als Lead vorhanden
            </>
          )}
          {result.errors.length > 0 && (
            <ul className="mt-2 list-disc pl-4 text-brand-danger-soft">
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
