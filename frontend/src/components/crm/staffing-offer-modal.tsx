"use client";

// NOMICON: "Als Einsatz anbieten" (Direct -> Überlassung) am Kandidaten und am Prozess: legt das
// Leiharbeitnehmer-Profil (Anwärter) und optional einen geplanten Einsatz an. Ist der Kandidat schon
// im Austausch, erscheint der Hinweis mit Bestätigung (oder die Sperre, je nach Einstellung).
import { useState } from "react";
import { useRouter } from "next/navigation";
import { HardHat } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { SearchSelect } from "@/components/ui/search-select";
import { ErrorBanner } from "@/components/crm/error-banner";
import { EngagementConflictNotice } from "@/components/crm/engagement-conflict-notice";
import { isEngagementConflict } from "@/lib/api/engagement";
import { isOverlapConflict } from "@/lib/staffing-deadline-text";
import { refreshEngagement } from "@/lib/api/engagement-hooks";
import { searchClients } from "@/lib/api/search-select-helpers";
import { invalidateStaffing } from "@/lib/api/staffing-hooks";
import { offerCandidateAsAssignment } from "@/lib/api/staffing";
import { useMyViews } from "@/lib/api/views-hooks";
import { cn } from "@/lib/utils";
import { labelClass } from "./staffing-ui";

export function OfferAsAssignmentButton({
  candidateId,
  clientId,
  iconOnly = false,
  className,
  iconSize = 14,
}: {
  candidateId: string;
  clientId?: string | null;
  iconOnly?: boolean;
  className?: string;
  iconSize?: number;
}) {
  const { data } = useMyViews();
  const [open, setOpen] = useState(false);
  if (!data?.data.views.includes("staffing")) return null; // ohne Ansicht Überlassung gibt es das nicht
  return (
    <>
      {iconOnly ? (
        <button
          type="button"
          title="Als Einsatz anbieten (Überlassung)"
          onClick={(event) => { event.stopPropagation(); setOpen(true); }}
          className={cn(className, "hover:bg-white/10 hover:text-white")}
        >
          <HardHat size={iconSize} />
        </button>
      ) : (
        <Button variant="outline" size="sm" onClick={() => setOpen(true)} className={className}>
          <HardHat size={iconSize} />Als Einsatz anbieten
        </Button>
      )}
      {open && <StaffingOfferModal candidateId={candidateId} defaultClientId={clientId ?? ""} onClose={() => setOpen(false)} />}
    </>
  );
}

function StaffingOfferModal({ candidateId, defaultClientId, onClose }: { candidateId: string; defaultClientId: string; onClose: () => void }) {
  const router = useRouter();
  const [clientId, setClientId] = useState(defaultClientId);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);

  async function send(confirm: boolean) {
    setBusy(true);
    setError(null);
    setConflict(null);
    try {
      if (Boolean(clientId) !== Boolean(start)) throw new Error("Für einen Einsatz sind Kunde und Beginn nötig – oder beides leer lassen.");
      const result = await offerCandidateAsAssignment(
        { candidate_id: candidateId, client_company_id: clientId || null, start_date: start || null, planned_end_date: end || null },
        confirm,
        confirm,
      );
      await Promise.all([invalidateStaffing(), refreshEngagement(candidateId)]);
      router.push(result.assignment_id ? `/ueberlassung/einsaetze/${result.assignment_id}` : `/ueberlassung/leiharbeitnehmer/${result.worker_id}`);
    } catch (exception) {
      const message = exception instanceof Error ? exception.message : "Anbieten fehlgeschlagen.";
      if ((isEngagementConflict(message) && !message.includes("gesperrt")) || isOverlapConflict(message)) setConflict(message);
      else setError(message);
      setBusy(false);
    }
  }

  return (
    <Modal title="Als Einsatz anbieten" eyebrow="Überlassung" onClose={onClose} maxWidth="max-w-lg">
      <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); void send(false); }}>
        <p className="text-sm text-brand-soft">
          Legt den Kandidaten als Leiharbeitnehmer-<strong>Anwärter</strong> an. Mit Kunde und Beginn entsteht zusätzlich ein <strong>geplanter Einsatz</strong>; die Checkliste folgt wie gewohnt. Der Kandidat bleibt im gemeinsamen Pool.
        </p>
        <div>
          <label className={labelClass}>Kunde (optional)</label>
          <SearchSelect value={clientId} onChange={setClientId} onSearch={searchClients} placeholder="Kunde suchen…" clearLabel="Noch offen" emptyLabel="Kein Kunde gefunden" />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass} htmlFor="of-start">Beginn</label><Input id="of-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="of-end">Geplantes Ende</label><Input id="of-end" type="date" min={start || undefined} value={end} onChange={(e) => setEnd(e.target.value)} /></div>
        </div>
        <ErrorBanner message={error} />
        {conflict && <EngagementConflictNotice message={conflict} busy={busy} onConfirm={() => void send(true)} onCancel={() => setConflict(null)} />}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Abbrechen</Button>
          <Button type="submit" disabled={busy}>{busy ? "Anlegen…" : "Anbieten"}</Button>
        </div>
      </form>
    </Modal>
  );
}
