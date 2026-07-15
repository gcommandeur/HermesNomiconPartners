"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { SearchSelect } from "@/components/ui/search-select";
import { apiPost } from "@/lib/api/client";
import type { Candidate, CandidateSubmission, ClientCompany } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-[#94A3B8]";

export function SubmissionCreateForm({
  candidates,
  clients,
  onDone,
}: {
  candidates: Candidate[];
  clients: ClientCompany[];
  onDone: (submission: CandidateSubmission) => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidateId, setCandidateId] = useState("");
  const [clientId, setClientId] = useState("");

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (!candidateId) throw new Error("Bitte einen Kandidaten auswählen.");
      const submission = await apiPost<CandidateSubmission>("/submissions", {
        candidate_id: candidateId,
        client_company_id: clientId || undefined,
      });
      setCandidateId("");
      setClientId("");
      router.refresh();
      onDone(submission);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Prozess konnte nicht angelegt werden.");
    } finally {
      setBusy(false);
    }
  }

  const candidateOptions = candidates.map((candidate) => ({
    value: candidate.id,
    label: `${candidate.first_name} ${candidate.last_name}`,
    sublabel: candidate.candidate_number ? `Nr. ${candidate.candidate_number}` : undefined,
  }));
  const clientOptions = clients
    .filter((client) => client.status !== "blocked")
    .map((client) => ({ value: client.id, label: client.name, sublabel: client.kanzleigruppe ?? client.city ?? undefined }));

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div>
        <label className={labelClass}>Kandidat *</label>
        <SearchSelect
          required
          options={candidateOptions}
          value={candidateId}
          onChange={setCandidateId}
          placeholder="Name oder Kandidatennummer suchen…"
          emptyLabel="Kein Kandidat gefunden"
        />
      </div>
      <div>
        <label className={labelClass}>Kanzlei (optional)</label>
        <SearchSelect
          options={clientOptions}
          value={clientId}
          onChange={setClientId}
          placeholder="Kanzlei suchen…"
          emptyLabel="Keine Kanzlei gefunden"
          clearLabel="Noch offen"
        />
      </div>
      {error && <div className="rounded-lg border border-red-400/25 bg-red-950/30 p-3 text-xs text-red-200">{error}</div>}
      <div className="flex justify-end gap-2">
        <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Prozess erstellen"}</Button>
      </div>
    </form>
  );
}

export function SubmissionCreateModal({
  candidates,
  clients,
  onCreated,
}: {
  candidates: Candidate[];
  clients: ClientCompany[];
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
          <SubmissionCreateForm candidates={candidates} clients={clients} onDone={(submission) => { setOpen(false); onCreated?.(submission); }} />
        </Modal>
      )}
    </>
  );
}
