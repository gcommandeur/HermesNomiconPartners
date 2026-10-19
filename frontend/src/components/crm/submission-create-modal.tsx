"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { SearchSelect } from "@/components/ui/search-select";
import { apiPost } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import { searchCandidates, searchClients } from "@/lib/api/search-select-helpers";
import { useAssignableUsersCache, useCurrentUser } from "@/lib/api/hooks";
import type { CandidateSubmission } from "@/lib/api/types";
import { EngagementConflictNotice } from "@/components/crm/engagement-conflict-notice"; // NOMICON
import { isEngagementConflict } from "@/lib/api/engagement"; // NOMICON

const labelClass = "mb-1 block text-xs text-brand-muted";
const selectClass = "h-10 w-full rounded-md border border-white/10 bg-brand-surface px-3 text-sm text-brand-text outline-none focus:border-brand-accent";

export function SubmissionCreateForm({
  onDone,
}: {
  onDone: (submission: CandidateSubmission) => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null); // NOMICON
  const [candidateId, setCandidateId] = useState("");
  const [clientId, setClientId] = useState("");
  const [ownerUserIdSelection, setOwnerUserIdSelection] = useState("");
  const { data: currentUserData } = useCurrentUser();
  const { data: assignableUsersData } = useAssignableUsersCache();
  const assignableUsers = assignableUsersData?.data ?? [];
  // Default = aktuell eingeloggter Nutzer (aber im Dropdown aenderbar).
  const ownerUserId = ownerUserIdSelection || currentUserData?.data.id || "";

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    await send(false);
  }

  async function send(confirmEngagement: boolean) {
    setBusy(true);
    setError(null);
    setConflict(null);
    try {
      if (!candidateId) throw new Error("Bitte einen Kandidaten auswählen.");
      const submission = await apiPost<CandidateSubmission>(`/submissions${confirmEngagement ? "?confirm_engagement=true" : ""}`, {
        candidate_id: candidateId,
        client_company_id: clientId || undefined,
        owner_user_id: ownerUserId || undefined,
      });
      setCandidateId("");
      setClientId("");
      setOwnerUserIdSelection("");
      router.refresh();
      onDone(submission);
    } catch (exception) {
      const message = exception instanceof Error ? exception.message : "Prozess konnte nicht angelegt werden.";
      // NOMICON: Kandidat ist bereits im Austausch -> Hinweis mit Bestätigung statt Fehler
      if (isEngagementConflict(message) && !message.includes("gesperrt")) setConflict(message);
      else setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div>
        <label className={labelClass}>Kandidat *</label>
        <SearchSelect
          required
          onSearch={searchCandidates}
          value={candidateId}
          onChange={setCandidateId}
          placeholder="Name oder Kandidatennummer suchen…"
          emptyLabel="Kein Kandidat gefunden"
        />
      </div>
      <div>
        <label className={labelClass}>Kunde (optional)</label>
        <SearchSelect
          onSearch={searchClients}
          value={clientId}
          onChange={setClientId}
          placeholder="Kunde suchen…"
          emptyLabel="Keinen Kunden gefunden"
          clearLabel="Noch offen"
        />
      </div>
      <div>
        <label className={labelClass}>Zuständiger Mitarbeiter</label>
        <select className={selectClass} value={ownerUserId} onChange={(e) => setOwnerUserIdSelection(e.target.value)}>
          <option value="">Nicht zugewiesen</option>
          {assignableUsers.map((user) => (
            <option key={user.id} value={user.id}>{user.display_name ?? user.email}</option>
          ))}
        </select>
      </div>
      <ErrorBanner message={error} />
      {conflict && <EngagementConflictNotice message={conflict} busy={busy} onConfirm={() => void send(true)} onCancel={() => setConflict(null)} />} {/* NOMICON */}
      <div className="flex justify-end gap-2">
        <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Prozess erstellen"}</Button>
      </div>
    </form>
  );
}

export function SubmissionCreateModal({
  onCreated,
}: {
  onCreated?: (submission: CandidateSubmission) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}><Plus size={15} />Prozess erstellen</Button>
      {open && (
        <Modal
          title="Prozess erstellen"
          eyebrow="Recruiting-Prozesse"
          description="Ein Prozess beginnt beim Quali Call. Der Kunde kann optional sofort verknüpft oder erst ab Interview ergänzt werden."
          onClose={() => setOpen(false)}
        >
          <SubmissionCreateForm onDone={(submission) => { setOpen(false); onCreated?.(submission); }} />
        </Modal>
      )}
    </>
  );
}
