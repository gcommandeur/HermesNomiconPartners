"use client";

import { useEffect, useMemo, useState } from "react";
import { ShieldOff, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorState } from "@/components/crm/error-state";
import { ErrorBanner } from "@/components/crm/error-banner";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCurrentUser, useDeletionRequestsCache } from "@/lib/api/hooks";
import { completeDeletionRequest, createDeletionRequest, getCandidates } from "@/lib/api/queries";
import { formatDateTime } from "@/lib/utils";
import type { Candidate } from "@/lib/api/types";

const selectClass =
  "h-9 w-full rounded-md border border-white/10 bg-brand-sidebar px-2 text-xs text-brand-text outline-none focus:border-brand-accent";

/** Loeschanfragen-Nachverfolgung (Art. 17 DSGVO, Punkt 3 des Auftrags "5
 * Hoch-Punkte umsetzen") - bewusst NUR eine Nachverfolgung UM die
 * bestehende Anonymisierung herum: "Erledigen" ruft weiterhin denselben,
 * unveraenderten Anonymisieren-Endpunkt auf (siehe Backend
 * services/deletion_requests.py), diese Seite fuegt lediglich Deadline-
 * Tracking und eine Liste drumherum hinzu. */
function daysRemainingLabel(deadline: string): { text: string; overdue: boolean } {
  const diffMs = new Date(deadline).getTime() - Date.now();
  const days = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  if (days < 0) return { text: `${Math.abs(days)} Tag(e) überfällig`, overdue: true };
  if (days === 0) return { text: "Heute fällig", overdue: true };
  return { text: `${days} Tag(e) verbleibend`, overdue: false };
}

export default function DeletionRequestsPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const { data, isLoading, error, mutate: retry } = useDeletionRequestsCache(isAdmin, true);
  const requests = data?.data ?? [];

  const [candidates, setCandidates] = useState<Candidate[]>([]);
  useEffect(() => {
    if (!isAdmin) return;
    void getCandidates().then((result) => setCandidates(result.data));
  }, [isAdmin]);
  const sortedCandidates = useMemo(
    () =>
      [...candidates].sort((a, b) =>
        `${a.last_name} ${a.first_name}`.localeCompare(`${b.last_name} ${b.first_name}`),
      ),
    [candidates],
  );

  const [newCandidateId, setNewCandidateId] = useState("");
  const [newRequestedVia, setNewRequestedVia] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [completingId, setCompletingId] = useState<string | null>(null);
  const [completeError, setCompleteError] = useState<string | null>(null);

  async function handleCreate() {
    if (!newCandidateId || !newRequestedVia.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      await createDeletionRequest({
        candidate_id: newCandidateId,
        requested_via: newRequestedVia.trim(),
      });
      setNewCandidateId("");
      setNewRequestedVia("");
      await retry();
    } catch (exception) {
      setCreateError(
        exception instanceof Error ? exception.message : "Löschanfrage konnte nicht angelegt werden.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleComplete(id: string, candidateName: string) {
    if (
      !window.confirm(
        `Löschanfrage für ${candidateName} erledigen? Das anonymisiert den Kandidaten unwiderruflich (Klarname/Kontaktdaten/CV werden entfernt).`,
      )
    ) {
      return;
    }
    setCompletingId(id);
    setCompleteError(null);
    try {
      await completeDeletionRequest(id);
      await retry();
    } catch (exception) {
      setCompleteError(
        exception instanceof Error ? exception.message : "Löschanfrage konnte nicht erledigt werden.",
      );
    } finally {
      setCompletingId(null);
    }
  }

  if (meLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-14 animate-pulse rounded-lg bg-brand-surface" />
        ))}
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow="Hermes" title="Löschanfragen" />
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ShieldOff size={28} className="text-brand-muted" />
            <p className="text-sm font-semibold text-brand-text">Nur für Admins zugänglich</p>
          </CardContent>
        </Card>
      </>
    );
  }

  if (error) {
    return <ErrorState onRetry={() => void retry()} />;
  }

  return (
    <>
      <PageHeader eyebrow="Hermes" title="Löschanfragen" />

      <div className="space-y-5">
        <Card>
          <CardHeader>
            <h2 className="font-semibold">Neue Löschanfrage anlegen</h2>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <select
                className={selectClass}
                value={newCandidateId}
                onChange={(e) => setNewCandidateId(e.target.value)}
              >
                <option value="">Kandidat auswählen…</option>
                {sortedCandidates.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.last_name}, {candidate.first_name}
                    {candidate.candidate_number ? ` (Nr. ${candidate.candidate_number})` : ""}
                  </option>
                ))}
              </select>
              <Input
                placeholder="Eingegangen via (z.B. E-Mail, Telefon)"
                value={newRequestedVia}
                onChange={(e) => setNewRequestedVia(e.target.value)}
              />
            </div>
            <ErrorBanner message={createError} />
            <Button
              size="sm"
              disabled={creating || !newCandidateId || !newRequestedVia.trim()}
              onClick={handleCreate}
            >
              {creating ? "Wird angelegt…" : "Löschanfrage anlegen"}
            </Button>
          </CardContent>
        </Card>

        <ErrorBanner message={completeError} />

        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="h-16 animate-pulse rounded-lg bg-brand-surface" />
            ))}
          </div>
        ) : requests.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-xs text-brand-muted">
              Keine offenen Löschanfragen.
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {requests.map((request) => {
              const { text: remainingText, overdue } = daysRemainingLabel(request.deadline);
              const candidateName = `${request.candidate_first_name} ${request.candidate_last_name}`;
              return (
                <Card key={request.id}>
                  <CardContent className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="font-semibold text-brand-text">
                        {candidateName}
                        {request.candidate_number ? ` (Nr. ${request.candidate_number})` : ""}
                      </p>
                      <p className="mt-1 text-xs text-brand-muted">
                        Angefragt am {formatDateTime(request.requested_at)} via {request.requested_via}
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right text-xs">
                        <p className="text-[10px] uppercase tracking-wider text-brand-muted">Deadline</p>
                        <p className={overdue ? "font-semibold text-red-400" : "text-brand-text"}>
                          {formatDateTime(request.deadline)}
                        </p>
                        <p className={overdue ? "font-semibold text-red-400" : "text-brand-muted"}>
                          {remainingText}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={completingId === request.id}
                        onClick={() => handleComplete(request.id, candidateName)}
                      >
                        <Trash2 size={13} />
                        {completingId === request.id ? "Wird erledigt…" : "Erledigen"}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
