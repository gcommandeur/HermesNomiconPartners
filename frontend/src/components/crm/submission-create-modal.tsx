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

const labelClass = "mb-1 block text-xs text-[#94A3B8]";
const selectClass = "h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

export function SubmissionCreateForm({
  onDone,
}: {
  onDone: (submission: CandidateSubmission) => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
    setBusy(true);
    setError(null);
    try {
      if (!candidateId) throw new Error("Bitte einen Kandidaten auswählen.");
      const submission = await apiPost<CandidateSubmission>("/submissions", {
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
      setError(exception instanceof Error ? exception.message : "Prozess konnte nicht angelegt werden.");
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
        <label className={labelClass}>Kanzlei (optional)</label>
        <SearchSelect
          onSearch={searchClients}
          value={clientId}
          onChange={setClientId}
          placeholder="Kanzlei suchen…"
          emptyLabel="Keine Kanzlei gefunden"
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
          description="Ein Prozess beginnt bei Quali Call. Die Kanzlei kann optional sofort verknüpft oder erst ab Interview ergänzt werden."
          onClose={() => setOpen(false)}
        >
          <SubmissionCreateForm onDone={(submission) => { setOpen(false); onCreated?.(submission); }} />
        </Modal>
      )}
    </>
  );
}
