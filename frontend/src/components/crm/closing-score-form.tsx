"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Gauge } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Badge } from "@/components/ui/badge";
import { apiPatch } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import type { ClosingScoreResult } from "@/lib/api/types";

const PAIN_OPTIONS = [
  { value: 0, label: "Kein klarer Wechselgrund" },
  { value: 1, label: "Leichte Unzufriedenheit" },
  { value: 2, label: "Wiederkehrender Frust" },
  { value: 3, label: "Klar benannter Nachteil" },
  { value: 4, label: "Spürbarer Leidensdruck" },
  { value: 5, label: 'Akuter Verlustdruck ("so nicht weiter")' },
];

const DECISION_OPTIONS = [
  { value: 0, label: '"Mal schauen"' },
  { value: 1, label: "Offen, ohne Ziel" },
  { value: 2, label: "Grundsätzlich interessiert" },
  { value: 3, label: "Wechsel ja, Zeitpunkt offen" },
  { value: 4, label: "Wechsel ja, Zeitraum genannt" },
  { value: 5, label: "Klares Ja + fixes Entscheidungsdatum" },
];

const MARKET_OPTIONS = [
  { value: 0, label: "Schwer platzierbar" },
  { value: 1, label: "Sehr erklärungsbedürftig" },
  { value: 2, label: "Durchschnittlich" },
  { value: 3, label: "Solider Fit" },
  { value: 4, label: "Gute Nachfrage" },
  { value: 5, label: "Klarer USP + hohe Nachfrage" },
];

const MOMENTUM_OPTIONS = [
  { value: 0, label: "Verzögert/Rückzug" },
  { value: 1, label: "Sehr träge" },
  { value: 2, label: "Langsam/passiv" },
  { value: 3, label: "Normal reaktiv" },
  { value: 4, label: "Schnell & reflektiert" },
  { value: 5, label: "Treibend & verbindlich" },
];

function StatementPicker({ title, options, value, onChange }: {
  title: string;
  options: { value: number; label: string }[];
  value: number | null;
  onChange: (value: number) => void;
}) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand-gray">{title}</p>
      <div className="space-y-1.5">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`block w-full rounded-md border px-3 py-2 text-left text-xs transition-colors ${
              value === option.value
                ? "border-brand-accent/60 bg-brand-accent-strong/60 text-brand-text"
                : "border-white/10 bg-brand-surface text-brand-soft hover:border-white/20"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

const closingStatusTone = { hot: "green", warm: "amber", risk: "blue", stop: "red" } as const;
const closingStatusLabel = { hot: "Hot", warm: "Warm", risk: "Risk", stop: "Stop" } as const;

export function ClosingScoreForm({ submissionId, onScored }: {
  submissionId: string;
  onScored?: (result: ClosingScoreResult) => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pain, setPain] = useState<number | null>(null);
  const [decision, setDecision] = useState<number | null>(null);
  const [market, setMarket] = useState<number | null>(null);
  const [momentum, setMomentum] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ClosingScoreResult | null>(null);

  async function handleSubmit() {
    if (pain === null || decision === null || market === null) return;
    setBusy(true);
    setError(null);
    try {
      const scored = await apiPatch<ClosingScoreResult>(
        `/submissions/${submissionId}/closing-score`,
        {
          pain_staerke: pain,
          entscheidungsklarheit: decision,
          markt_fit: market,
          momentum,
        },
      );
      setResult(scored);
      onScored?.(scored);
      router.refresh();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Bewertung fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}><Gauge size={13} />Closing-Score</Button>
      {open && (
        <Modal
          title="Closing-Probability nach Quali-Call"
          eyebrow="Bewertung"
          maxWidth="max-w-3xl"
          onClose={() => setOpen(false)}
        >
          {result ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <Badge tone={closingStatusTone[result.closing_status]}>{closingStatusLabel[result.closing_status]}</Badge>
                <span className="text-lg font-semibold">{result.closing_probability} %</span>
              </div>
              <p className="text-sm text-brand-soft">Empfehlung: {result.action_recommendation}</p>
              <div className="flex justify-end"><Button size="sm" onClick={() => setOpen(false)}>Schließen</Button></div>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
                <StatementPicker title="Pain-Stärke" options={PAIN_OPTIONS} value={pain} onChange={setPain} />
                <StatementPicker title="Entscheidungsklarheit" options={DECISION_OPTIONS} value={decision} onChange={setDecision} />
                <StatementPicker title="Markt-Fit" options={MARKET_OPTIONS} value={market} onChange={setMarket} />
              </div>
              <div className="border-t border-white/10 pt-4">
                <StatementPicker title="Momentum (optional, separates Formular)" options={MOMENTUM_OPTIONS} value={momentum} onChange={setMomentum} />
              </div>
              <ErrorBanner message={error} />
              <div className="flex justify-end">
                <Button
                  disabled={busy || pain === null || decision === null || market === null}
                  onClick={handleSubmit}
                >
                  {busy ? "Berechne…" : "Bewertung abschließen"}
                </Button>
              </div>
            </div>
          )}
        </Modal>
      )}
    </>
  );
}
