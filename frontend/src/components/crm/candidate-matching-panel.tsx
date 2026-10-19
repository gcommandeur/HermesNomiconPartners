"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw, Sparkles } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { apiPost } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import { getCandidateMatches } from "@/lib/api/queries";
import type { BulkSubmitResponse, ClientMatch } from "@/lib/api/types";

const STATUS_OPTIONS = [
  { value: "cv_out", label: "CV-Out" },
  { value: "cv_in", label: "CV-In" },
];

export function CandidateMatchingPanel({ candidateId }: { candidateId: string }) {
  const router = useRouter();
  const [matches, setMatches] = useState<ClientMatch[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [targetStatus, setTargetStatus] = useState("cv_out");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BulkSubmitResponse | null>(null);

  async function loadMatches({ resetResult = true }: { resetResult?: boolean } = {}) {
    setLoading(matches === null);
    setError(null);
    try {
      const response = await getCandidateMatches(candidateId);
      setMatches(response.data);
      setSelected(new Set());
      if (resetResult) setResult(null);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Matches konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMatches();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateId]);

  function toggle(clientId: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(clientId)) next.delete(clientId);
      else next.add(clientId);
      return next;
    });
  }

  async function handleBulkSubmit() {
    if (selected.size === 0) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiPost<BulkSubmitResponse>(`/candidates/${candidateId}/bulk-submit`, {
        client_company_ids: Array.from(selected),
        target_status: targetStatus,
      });
      setResult(response);
      router.refresh();
      await loadMatches({ resetResult: false });
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "CV-Outs konnten nicht angelegt werden.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Card><CardContent className="py-12 text-center text-sm text-brand-gray">Passende Kunden werden geladen…</CardContent></Card>;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-brand-soft"><Sparkles size={15} />Kunden nach Fachgebiet, Ort und PLZ sortiert.</div>
        <div className="flex items-center gap-2">
          <select className="h-9 rounded-md border border-white/10 bg-brand-surface px-2 text-xs text-brand-text outline-none focus:border-brand-accent" value={targetStatus} onChange={(e) => setTargetStatus(e.target.value)}>
            {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
          <Button size="sm" variant="outline" onClick={() => loadMatches()}><RefreshCw size={13} />Aktualisieren</Button>
          <Button size="sm" disabled={selected.size === 0 || busy} onClick={handleBulkSubmit}>{busy ? "Wird gesendet…" : `${selected.size} auswählen -> senden`}</Button>
        </div>
      </div>

      <ErrorBanner message={error} />

      {result && (
        <Card>
          <CardContent className="text-xs text-brand-soft">
            <p className="font-semibold text-brand-text">{result.created_count} CV-Out(s) angelegt, {result.skipped_count} übersprungen.</p>
            <ul className="mt-2 space-y-1">
              {result.results.map((item) => {
                const client = matches?.find((match) => match.client.id === item.client_company_id)?.client;
                return (
                  <li key={item.client_company_id} className={item.outcome === "created" ? "text-emerald-300" : "text-amber-300"}>
                    {client?.name ?? item.client_company_id}: {item.outcome === "created" ? "angelegt" : `übersprungen${item.reason ? ` (${item.reason})` : ""}`}
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>
      )}

      <div className="space-y-2">
        {matches?.map((match) => (
          <Card key={match.client.id}>
            <CardContent className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-1 size-4 shrink-0 accent-brand-accent"
                  checked={selected.has(match.client.id)}
                  disabled={match.already_submitted}
                  onChange={() => toggle(match.client.id)}
                />
                <div>
                  <p className="font-semibold">{match.client.name}</p>
                  <p className="mt-1 text-xs text-brand-muted">{match.client.city ?? match.client.postal_code ?? "Region offen"} · {match.client.focus ?? "Fokus offen"}</p>
                  {match.reasons.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {match.reasons.map((reason) => <span key={reason} className="rounded bg-brand-panel px-2 py-0.5 text-[9.5px] text-brand-muted">{reason}</span>)}
                    </div>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="rounded-full bg-brand-accent-soft px-3 py-1 text-xs font-semibold text-brand-platinum">Score {match.score}</span>
                {match.already_submitted && <span className="text-xs text-brand-gray">Bereits im Prozess</span>}
              </div>
            </CardContent>
          </Card>
        ))}
        {matches?.length === 0 && <Card><CardContent className="py-12 text-center text-sm text-brand-gray">Keine passenden Kunden gefunden.</CardContent></Card>}
      </div>
    </div>
  );
}
