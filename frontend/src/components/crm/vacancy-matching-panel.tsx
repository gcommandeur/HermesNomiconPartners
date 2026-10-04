"use client";

import { useEffect, useState } from "react";
import { RefreshCw, Sparkles } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/crm/error-banner";
import { getVacancyMatches } from "@/lib/api/queries";
import type { CandidateMatch } from "@/lib/api/types";

export function VacancyMatchingPanel({ vacancyId }: { vacancyId: string }) {
  const [matches, setMatches] = useState<CandidateMatch[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadMatches() {
    setLoading(matches === null);
    setError(null);
    try {
      const response = await getVacancyMatches(vacancyId);
      setMatches(response.data);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Matches konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMatches();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vacancyId]);

  if (loading) return <Card><CardContent className="py-8 text-center text-sm text-brand-gray">Passende Kandidaten werden geladen…</CardContent></Card>;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-brand-soft"><Sparkles size={13} />Nach Rolle, Umkreis und fachlicher Überschneidung sortiert.</div>
        <Button size="sm" variant="outline" onClick={() => loadMatches()}><RefreshCw size={12} />Aktualisieren</Button>
      </div>
      <ErrorBanner message={error} />
      <div className="space-y-2">
        {matches?.map((match) => (
          <Card key={match.candidate.id}>
            <CardContent className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
              <div>
                <p className="font-semibold">{match.candidate.first_name} {match.candidate.last_name}</p>
                <p className="mt-1 text-xs text-brand-muted">{match.candidate.city ?? match.candidate.postal_code ?? "Ort offen"} · {match.candidate.job_title ?? "Rolle offen"}</p>
                {match.reasons.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {match.reasons.map((reason) => <span key={reason} className="rounded bg-brand-panel px-2 py-0.5 text-[10px] text-brand-muted">{reason}</span>)}
                  </div>
                )}
              </div>
              <span className="shrink-0 rounded-full bg-brand-accent-soft px-3 py-1 text-xs font-semibold text-brand-platinum">Score {match.score}</span>
            </CardContent>
          </Card>
        ))}
        {matches?.length === 0 && <Card><CardContent className="py-8 text-center text-xs text-brand-gray">Keine passenden Kandidaten im Umkreis gefunden.</CardContent></Card>}
      </div>
    </div>
  );
}
