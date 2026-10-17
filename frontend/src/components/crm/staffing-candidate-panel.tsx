"use client";

// NOMICON: Überlassung - Reiter „Überlassung“ am Kandidaten: Profil anlegen oder Stand zeigen.
import { useState } from "react";
import Link from "next/link";
import { HardHat } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Pencil } from "lucide-react";
import { useCurrentUser } from "@/lib/api/hooks";
import { invalidateStaffing, useStaffingDeadlines, useStaffingDisposition, useStaffingWorkerForCandidate, useWorkerTimesheetSummary } from "@/lib/api/staffing-hooks";
import { formatDate } from "@/lib/utils";
import { candidateStaffingActions } from "@/lib/staffing-candidate";
import { StaffingAssignmentCreateButton } from "./staffing-assignment-create-modal";
import { StaffingAssignmentsView } from "./staffing-assignments-view";
import { EqualPayBox } from "./staffing-equal-pay";
import { StaffingPriorPeriodsSection } from "./staffing-prior-periods";
import { WorkerCreateFromCandidate, WorkerEditModal } from "./staffing-workers-view";
import { DeadlineMeter, Fact, LEGAL_NOTICE, LoadError, LoadingRows, WorkerStatusBadge } from "./staffing-ui";
import { formatHours } from "@/lib/format"; // NOMICON

/** Stundenzettel der Person nach Status, mit Link zur Abrechnung. */
function TimesheetStatus({ workerId }: { workerId: string }) {
  const { data } = useWorkerTimesheetSummary(workerId);
  const summary = data?.data;
  if (!summary) return null;
  const items = [
    ["Offen", summary.open],
    ["Beim Kunden", summary.submitted],
    ["Freigegeben", summary.approved],
    ["Abgelehnt", summary.rejected],
  ] as const;
  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="font-semibold">Stundenzettel</h3>
        <Link href="/ueberlassung/abrechnung" className="text-xs text-brand-muted underline hover:text-brand-platinum">Zur Abrechnung</Link>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {items.map(([label, count]) => (
          <Card key={label}><CardContent className="p-3"><p className="text-[10.45px] text-brand-muted">{label}</p><p className="mt-1 text-lg font-semibold">{count}</p></CardContent></Card>
        ))}
      </div>
      {summary.approved_unbilled > 0 && <p className="mt-2 text-xs text-brand-muted">{summary.approved_unbilled} freigegebene(r) Stundenzettel noch nicht abgerechnet.</p>}
    </section>
  );
}

export function StaffingCandidatePanel({ candidateId }: { candidateId: string }) {
  const { data: worker, error, isLoading, mutate } = useStaffingWorkerForCandidate(candidateId);
  const { data: deadlines } = useStaffingDeadlines();
  const { data: disposition } = useStaffingDisposition();
  const { data: me } = useCurrentUser();
  const isAdmin = me?.data.is_admin ?? false;
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(false);
  if (error) return <LoadError onRetry={() => void mutate()} />;
  if (isLoading || worker === undefined) return <LoadingRows rows={2} />;

  if (worker === null) {
    return (
      <div className="space-y-5">
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
      </div>
    );
  }

  const myDeadlines = (deadlines?.data ?? []).filter((d) => d.worker_id === worker.id);
  const benchEntry = (disposition?.data.bench ?? []).find((b) => b.worker_id === worker.id);

  return (
    <div className="space-y-5">
      {/* Direct und Überlassung nebeneinander (gemeinsamer Kandidatenstatus mit Konflikt-Hinweis) zeigt
          bereits der Kopfbereich der Kandidatenseite - hier nicht noch einmal. */}
      <Card>
        <CardContent>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <h2 className="font-semibold">Leiharbeitnehmer</h2>
              <WorkerStatusBadge status={worker.status} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Pencil size={14} />Bearbeiten</Button>
              <Button asChild size="sm" variant="outline"><Link href={`/ueberlassung/leiharbeitnehmer/${worker.id}`}>Zum Überlassungsprofil</Link></Button>
            </div>
          </div>
          {benchEntry && (
            <p className="mt-3 rounded-lg border border-brand-warning/40 bg-brand-warning/10 px-3 py-2 text-sm" role="status">
              Auf der Bench: kein aktiver oder geplanter Einsatz{benchEntry.free_since ? ` – frei seit ${formatDate(benchEntry.free_since)}` : ""}.
            </p>
          )}
          <div className="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-3">
            <Fact label="Eintritt">{worker.entry_date ? formatDate(worker.entry_date) : null}</Fact>
            <Fact label="Tarif-/Entgeltgruppe">{worker.pay_grade}</Fact>
            <Fact label="Wochenstunden">{worker.weekly_hours ? formatHours(worker.weekly_hours) : null}</Fact>
          </div>
        </CardContent>
      </Card>
      {editing && <WorkerEditModal worker={worker} isAdmin={isAdmin} onClose={() => { setEditing(false); void invalidateStaffing(); void mutate(); }} />}
      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="font-semibold">Einsätze</h3>
          {candidateStaffingActions(worker).newAssignment && <StaffingAssignmentCreateButton workerId={worker.id} />}
        </div>
        <StaffingAssignmentsView workerId={worker.id} />
      </section>
      <StaffingPriorPeriodsSection workerId={worker.id} />
      <section>
        <h3 className="mb-3 font-semibold">Fristen je Kunde</h3>
        {myDeadlines.length === 0 ? (
          <p className="text-sm text-brand-muted">Keine laufende Überlassung – es zählt noch keine Frist.</p>
        ) : (
          <div className="space-y-3">
            {myDeadlines.map((deadline) => (
              <Card key={`${deadline.worker_id}:${deadline.client_company_id}`}>
                <CardContent>
                  <p className="mb-2 text-sm font-semibold">{deadline.client_name}</p>
                  <DeadlineMeter deadline={deadline} />
                  <EqualPayBox assignmentId={deadline.assignment_id} deadline={deadline} />
                  <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
                    <Fact label="Spätester Einsatztag">{deadline.max_end_date ? formatDate(deadline.max_end_date) : null}</Fact>
                    <Fact label="Equal Pay ab">{deadline.equal_pay_from ? formatDate(deadline.equal_pay_from) : null}</Fact>
                    <Fact label="Zähler seit">{deadline.chain_start ? formatDate(deadline.chain_start) : null}</Fact>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
        <p className="mt-2 text-xs text-brand-muted">{LEGAL_NOTICE}</p>
      </section>
      <TimesheetStatus workerId={worker.id} />
      <p className="text-xs text-brand-muted">Übernahme durch den Kunden: Honorar-Staffel und Vorschau am Einsatz (Aktion „Übernahme“), Staffelwerte unter <Link href="/ueberlassung/compliance" className="underline">Compliance</Link>.</p>
    </div>
  );
}
