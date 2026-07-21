"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { UserPlus } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiPost } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import { invalidateContactsCache, useClientsCache } from "@/lib/api/hooks";
import type { Contact } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-[#94A3B8]";

export function ContactCreateModal({ onCreated }: { onCreated?: (contact: Contact) => void }) {
  const router = useRouter();
  const { data: clientsData } = useClientsCache();
  const clients = clientsData?.data ?? [];
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    client_company_id: clients[0]?.id ?? "",
    first_name: "",
    last_name: "",
    role_title: "",
    email: "",
    phone: "",
    is_primary: false,
  });

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (!form.client_company_id) throw new Error("Bitte eine Kanzlei auswählen.");
      const contact = await apiPost<Contact>("/contacts", {
        ...form,
        role_title: form.role_title || undefined,
        email: form.email || undefined,
        phone: form.phone || undefined,
      });
      setOpen(false);
      setForm({ client_company_id: clients[0]?.id ?? "", first_name: "", last_name: "", role_title: "", email: "", phone: "", is_primary: false });
      onCreated?.(contact);
      router.refresh();
      void invalidateContactsCache();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Kontakt konnte nicht angelegt werden.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button onClick={() => setOpen(true)}><UserPlus size={15} />Kontakt anlegen</Button>
      {open && (
        <Modal title="Kontakt anlegen" eyebrow="Kanzlei-Beziehungsnetz" onClose={() => setOpen(false)}>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className={labelClass}>Kanzlei *</label>
              <select
                required
                className="h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]"
                value={form.client_company_id}
                onChange={(e) => set("client_company_id", e.target.value)}
              >
                <option value="" disabled>Kanzlei wählen…</option>
                {clients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div><label className={labelClass}>Vorname *</label><Input required value={form.first_name} onChange={(e) => set("first_name", e.target.value)} /></div>
              <div><label className={labelClass}>Nachname *</label><Input required value={form.last_name} onChange={(e) => set("last_name", e.target.value)} /></div>
            </div>
            <div><label className={labelClass}>Rolle</label><Input value={form.role_title} onChange={(e) => set("role_title", e.target.value)} /></div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div><label className={labelClass}>E-Mail</label><Input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} /></div>
              <div><label className={labelClass}>Telefon</label><Input value={form.phone} onChange={(e) => set("phone", e.target.value)} /></div>
            </div>
            <label className="flex items-center gap-2 text-xs text-[#CBD5E1]">
              <input type="checkbox" checked={form.is_primary} onChange={(e) => set("is_primary", e.target.checked)} />
              Hauptkontakt dieser Kanzlei
            </label>
            <ErrorBanner message={error} />
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>Abbrechen</Button>
              <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Kontakt anlegen"}</Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
