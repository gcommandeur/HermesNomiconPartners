"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Pencil, Plus, TriangleAlert } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiPatch, apiPost } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import { invalidateClientsCache, useAssignableUsersCache, useCurrentUser } from "@/lib/api/hooks";
import { checkClientDuplicate } from "@/lib/api/queries";
import type { ClientCompany, ClientDuplicateCandidate } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-[#94A3B8]";
const selectClass = "h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";
const emptyForm = {
  name: "", kanzleigruppe: "", status: "prospect", website: "", email: "", phone: "",
  street: "", city: "", postal_code: "", region: "", focus: "", company_size: "",
  fee_percentage: "27.00", honorar_stufe: "standard", nachlass_begruendung: "", agb_version: "",
  owner_user_id: "",
};

function formFromClient(client: ClientCompany): typeof emptyForm {
  return {
    name: client.name ?? "",
    kanzleigruppe: client.kanzleigruppe ?? "",
    status: client.status ?? "acquisition",
    website: client.website ?? "",
    email: client.email ?? "",
    phone: client.phone ?? "",
    street: client.street ?? "",
    city: client.city ?? "",
    postal_code: client.postal_code ?? "",
    region: client.region ?? "",
    focus: client.focus ?? "",
    company_size: client.company_size ?? "",
    fee_percentage: String(client.fee_percentage ?? "27.00"),
    honorar_stufe: client.honorar_stufe ?? "standard",
    nachlass_begruendung: client.nachlass_begruendung ?? "",
    agb_version: client.agb_version ?? "",
    owner_user_id: client.owner_user_id ?? "",
  };
}

const honorarStufeOptions: { value: string; label: string }[] = [
  { value: "standard", label: "Standard (27 %) — größere/etablierte Kanzleien" },
  { value: "nachlass_1", label: "Nachlass 1 (25 %) — kleinere Kanzlei, begrenztes Budget" },
  { value: "nachlass_2", label: "Nachlass 2 (23 %) — sehr kleine/Einzelkanzlei" },
  { value: "individuell", label: "Individuell" },
];

export function ClientCreateForm({
  onDone,
  client,
}: {
  onDone: (client: ClientCompany) => void;
  client?: ClientCompany;
}) {
  const router = useRouter();
  const isEdit = Boolean(client);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState(client ? formFromClient(client) : emptyForm);
  const [duplicates, setDuplicates] = useState<ClientDuplicateCandidate[]>([]);
  const { data: currentUserData } = useCurrentUser();
  const { data: assignableUsersData } = useAssignableUsersCache();
  const assignableUsers = assignableUsersData?.data ?? [];
  const ownerUserId = form.owner_user_id || (isEdit ? "" : currentUserData?.data.id ?? "");

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  // Warnt (nicht blockierend) vor bestehenden Kanzleien mit ähnlichem Namen -
  // z.B. eine versehentlich doppelt erfasste Kanzlei. Mehrere Standorte
  // derselben Marke (andere PLZ) sind ausdrücklich erwünscht und werden hier
  // nur informativ mit angezeigt, nicht verhindert.
  useEffect(() => {
    const name = form.name.trim();
    if (name.length < 3) {
      setDuplicates([]);
      return;
    }
    const timeout = setTimeout(() => {
      checkClientDuplicate(name, form.postal_code.trim() || undefined, client?.id)
        .then(setDuplicates)
        .catch(() => setDuplicates([]));
    }, 400);
    return () => clearTimeout(timeout);
  }, [form.name, form.postal_code, client?.id]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // Leere Felder werden zu null (gültig für optionale Felder wie email),
      // statt als "" ans Backend geschickt zu werden - "" ist z.B. keine gültige
      // E-Mail und wurde vom Backend mit 422 abgelehnt, sobald im
      // Bearbeiten-Modus gespeichert wurde (betraf jede Kanzlei ohne E-Mail).
      const payload = Object.fromEntries(
        Object.entries(form)
          .filter(([, value]) => (isEdit ? true : value.trim() !== ""))
          .map(([key, value]) => [key, value.trim() === "" ? null : value]),
      );
      const result = isEdit
        ? await apiPatch<ClientCompany>(`/clients/${client!.id}`, payload)
        : await apiPost<ClientCompany>("/clients", payload);
      if (!isEdit) setForm(emptyForm);
      router.refresh();
      void invalidateClientsCache();
      onDone(result);
    } catch (exception) {
      setError(
        exception instanceof Error
          ? exception.message
          : isEdit
            ? "Änderungen konnten nicht gespeichert werden."
            : "Kanzlei konnte nicht angelegt werden.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={labelClass}>Name *</label><Input required value={form.name} onChange={(e) => set("name", e.target.value)} /></div>
        <div>
          <label className={labelClass}>Kanzleigruppe / Marke</label>
          <Input placeholder="z.B. ECOVIS, Afileon" value={form.kanzleigruppe} onChange={(e) => set("kanzleigruppe", e.target.value)} />
        </div>
      </div>
      {duplicates.length > 0 && (
        <div className="rounded-lg border border-[#F0B429]/25 bg-[#F0B429]/5 p-3 text-xs text-[#F0B429]">
          <div className="mb-1.5 flex items-center gap-1.5 font-semibold"><TriangleAlert size={13} />Ähnliche Kanzlei(en) bereits vorhanden</div>
          <ul className="space-y-0.5 text-[#F5D68A]">
            {duplicates.map((dup) => (
              <li key={dup.id}>
                {dup.name}{dup.kanzleigruppe ? ` (${dup.kanzleigruppe})` : ""} — {dup.city ?? "Ort unbekannt"}
                {dup.same_location ? " · gleiche PLZ, evtl. echtes Duplikat" : " · anderer Standort, evtl. gewollt"}
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-[#94A3B8]">Nur ein Hinweis — mehrere Standorte derselben Marke sind ausdrücklich erlaubt.</p>
          {!form.kanzleigruppe.trim() && duplicates.some((dup) => dup.kanzleigruppe) && (
            <button
              type="button"
              className="mt-2 rounded-md border border-[#1F5FA8]/40 bg-[#153A66]/45 px-2.5 py-1 text-[11px] text-[#c5dcfa] hover:bg-[#153A66]/70"
              onClick={() => set("kanzleigruppe", duplicates.find((dup) => dup.kanzleigruppe)?.kanzleigruppe ?? "")}
            >
              Kanzleigruppe &quot;{duplicates.find((dup) => dup.kanzleigruppe)?.kanzleigruppe}&quot; übernehmen
            </button>
          )}
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass}>Status</label>
          <select className={selectClass} value={form.status} onChange={(e) => set("status", e.target.value)}>
            <option value="prospect">Noch kein Kontakt (grau)</option>
            <option value="acquisition">In Verhandlung / unklar (gelb)</option>
            <option value="active">Aktive Kundenbeziehung (grün)</option>
            <option value="blocked">Kein Kontakt / Do not touch (rot)</option>
            <option value="archived">Archiviert</option>
          </select>
        </div>
        <div><label className={labelClass}>Fokus</label><Input value={form.focus} onChange={(e) => set("focus", e.target.value)} /></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={labelClass}>E-Mail</label><Input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} /></div>
        <div><label className={labelClass}>Telefon</label><Input value={form.phone} onChange={(e) => set("phone", e.target.value)} /></div>
      </div>
      <div><label className={labelClass}>Website</label><Input value={form.website} onChange={(e) => set("website", e.target.value)} /></div>
      <div><label className={labelClass}>Straße</label><Input value={form.street} onChange={(e) => set("street", e.target.value)} /></div>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={labelClass}>PLZ</label><Input value={form.postal_code} onChange={(e) => set("postal_code", e.target.value)} /></div>
        <div><label className={labelClass}>Ort</label><Input value={form.city} onChange={(e) => set("city", e.target.value)} /></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={labelClass}>Region</label><Input value={form.region} onChange={(e) => set("region", e.target.value)} /></div>
        <div><label className={labelClass}>Kanzleigröße</label><Input value={form.company_size} onChange={(e) => set("company_size", e.target.value)} /></div>
      </div>
      <div className="border-t border-white/10 pt-4">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-[#92979c]">Honorar</p>
        <div className="grid grid-cols-2 gap-3">
          <div><label className={labelClass}>Honorarsatz (%)</label><Input type="number" step="0.01" value={form.fee_percentage} onChange={(e) => set("fee_percentage", e.target.value)} /></div>
          <div>
            <label className={labelClass}>Honorar-Stufe</label>
            <select className={selectClass} value={form.honorar_stufe} onChange={(e) => set("honorar_stufe", e.target.value)}>
              {honorarStufeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div><label className={labelClass}>Nachlass-Begründung</label><Input placeholder="z.B. kleine Kanzlei, begrenztes Budget" value={form.nachlass_begruendung} onChange={(e) => set("nachlass_begruendung", e.target.value)} /></div>
          <div><label className={labelClass}>AGB-Version</label><Input value={form.agb_version} onChange={(e) => set("agb_version", e.target.value)} /></div>
        </div>
      </div>
      <div>
        <label className={labelClass}>Zuständiger Mitarbeiter</label>
        <select className={selectClass} value={ownerUserId} onChange={(e) => set("owner_user_id", e.target.value)}>
          <option value="">Nicht zugewiesen</option>
          {assignableUsers.map((user) => (
            <option key={user.id} value={user.id}>{user.display_name ?? user.email}</option>
          ))}
        </select>
      </div>
      <ErrorBanner message={error} />
      <div className="flex justify-end gap-2">
        <Button type="submit" disabled={busy}>
          {busy ? "Speichern…" : isEdit ? "Änderungen speichern" : "Kanzlei anlegen"}
        </Button>
      </div>
    </form>
  );
}

export function ClientCreateModal({ onCreated }: { onCreated?: (client: ClientCompany) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}><Plus size={15} />Kanzlei anlegen</Button>
      {open && (
        <Modal title="Kanzlei anlegen" eyebrow="Client Intelligence" onClose={() => setOpen(false)}>
          <ClientCreateForm onDone={(client) => { setOpen(false); onCreated?.(client); }} />
        </Modal>
      )}
    </>
  );
}

export function ClientEditModal({
  client,
  onUpdated,
}: {
  client: ClientCompany;
  onUpdated?: (client: ClientCompany) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}><Pencil size={13} />Bearbeiten</Button>
      {open && (
        <Modal title="Kanzlei bearbeiten" eyebrow="Client Intelligence" onClose={() => setOpen(false)}>
          <ClientCreateForm client={client} onDone={(updated) => { setOpen(false); onUpdated?.(updated); }} />
        </Modal>
      )}
    </>
  );
}
