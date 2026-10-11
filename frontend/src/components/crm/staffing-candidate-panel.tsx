"use client";

// NOMICON: Überlassung - Reiter „Überlassung“ am Kandidaten: Profil anlegen oder Stand zeigen.
import { useState } from "react";
import Link from "next/link";
import { HardHat } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { invalidateStaffing, useStaffingWorkerForCandidate } from "@/lib/api/staffing-hooks";
import { formatDate } from "@/lib/utils";
import { StaffingAssignmentsView } from "./staffing-assignments-view";
import { WorkerCreateFromCandidate } from "./staffing-workers-view";
import { Fact, LoadError, LoadingRows, WorkerStatusBadge } from "./staffing-ui";

export function StaffingCandidatePanel({ candidateId }: { candidateId: string }) {
  const { data: worker, error, isLoading, mutate } = useStaffingWorkerForCandidate(candidateId);
  const [creating, setCreating] = useState(false);
  if (error) return <LoadError onRetry={() => void mutate()} />;
  if (isLoading || worker === undefined) return <LoadingRows rows={2} />;

  if (worker === null) {
    return (
      <Card>
        <CardContent className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <HardHat size={20} className="mt-0.5 text-brand-silver" aria-hidden />
            <div>
              <h2 className="font-semibold">Kein Überlassungsprofil</h2>
              <p className="mt-1 text-sm text-brand-soft">
                Dieser Kandidat ist (noch) kein Leiharbeitnehmer. Der Kandidat bleibt im gemeinsamen Pool; das Überlassungsprofil kommt zusätzlich dazu.
              </p>
            </div>
          </div>
          <Button onClick={() => setCreating(true)}>Als Leiharbeitnehmer anlegen</Button>
        </CardContent>
        {creating && (
          <WorkerCreateFromCandidate
            candidateId={candidateId}
            onClose={() => setCreating(false)}
            onCreated={() => { setCreating(false); void invalidateStaffing(); void mutate(); }}
          />
        )}
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardContent>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <h2 className="font-semibold">Leiharbeitnehmer</h2>
              <WorkerStatusBadge status={worker.status} />
            </div>
            <Button asChild size="sm" variant="outline"><Link href={`/ueberlassung/leiharbeitnehmer/${worker.id}`}>Zum Überlassungsprofil</Link></Button>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-3">
            <Fact label="Eintritt">{worker.entry_date ? formatDate(worker.entry_date) : null}</Fact>
            <Fact label="Tarif-/Entgeltgruppe">{worker.pay_grade}</Fact>
            <Fact label="Wochenstunden">{worker.weekly_hours}</Fact>
          </div>
        </CardContent>
      </Card>
      <section>
        <h3 className="mb-3 font-semibold">Einsätze</h3>
        <StaffingAssignmentsView workerId={worker.id} />
      </section>
    </div>
  );
}
