"use client";

import { useMemo, useState } from "react";
import { Star } from "lucide-react";
import { FilterBar } from "@/components/crm/filter-bar";
import { DataTable } from "@/components/crm/data-table";
import { StatusPill } from "@/components/crm/status-pill";
import { ExportActions } from "@/components/crm/export-actions";
import { DemoNotice } from "@/components/crm/demo-notice";
import { ErrorState } from "@/components/crm/error-state";
import { useClientsCache, useContactsCache } from "@/lib/api/hooks";
import { AddToMailingButton } from "@/components/crm/add-to-mailing-button";
import { contactName } from "@/lib/utils";

export function ContactsTable() {
  const {
    data: contactsData,
    isLoading: contactsLoading,
    error: contactsError,
    mutate: retryContacts,
  } = useContactsCache();
  const {
    data: clientsData,
    isLoading: clientsLoading,
    error: clientsError,
    mutate: retryClients,
  } = useClientsCache();
  const contacts = useMemo(() => contactsData?.data ?? [], [contactsData]);
  const clients = useMemo(() => clientsData?.data ?? [], [clientsData]);
  const [search, setSearch] = useState("");
  const clientName = (id: string) => clients.find((client) => client.id === id)?.name ?? "Kanzlei";

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return contacts;
    return contacts.filter((contact) => {
      const haystack = [
        contactName(contact), clientName(contact.client_company_id), contact.role_title, contact.email,
      ].filter(Boolean).join(" ").toLowerCase();
      return haystack.includes(term);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contacts, search, clients]);

  const exportRows = useMemo(() => filtered.map((contact) => ({
    Name: contactName(contact),
    Kanzlei: clientName(contact.client_company_id),
    Rolle: contact.role_title,
    Email: contact.email,
    Telefon: contact.phone,
    Hauptkontakt: contact.is_primary ? "Ja" : "Nein",
    // eslint-disable-next-line react-hooks/exhaustive-deps
  })), [filtered]);

  if (contactsError || clientsError) {
    return <ErrorState onRetry={() => { void retryContacts(); void retryClients(); }} />;
  }

  if (contactsLoading || clientsLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, index) => (
          <div key={index} className="h-14 animate-pulse rounded-lg bg-[#0D1B2E]" />
        ))}
      </div>
    );
  }

  return (
    <>
      <div className="mb-4 flex justify-end"><ExportActions filename="kontakte" rows={exportRows} /></div>
      <DemoNotice source={contactsData?.source ?? "api"} error={contactsData?.error} />
      <FilterBar placeholder="Nach Name, Kanzlei oder Rolle suchen" value={search} onChange={setSearch} />
      <DataTable headers={["Kontakt", "Kanzlei", "Rolle", "E-Mail", "Telefon", "Hauptkontakt", "Mailing"]}>
        {filtered.map((contact) => (
          <tr key={contact.id} className="hover:bg-[#203A5A]/35">
            <td className="px-4 py-3.5 font-semibold text-[#D8DADF]">{contactName(contact)}</td>
            <td className="px-4 py-3.5">{clientName(contact.client_company_id)}</td>
            <td className="px-4 py-3.5">{contact.role_title ?? "—"}</td>
            <td className="px-4 py-3.5">{contact.email ?? "—"}</td>
            <td className="px-4 py-3.5">{contact.phone ?? "—"}</td>
            <td className="px-4 py-3.5">{contact.is_primary ? <span className="inline-flex items-center gap-1 rounded-full border border-[#D8DADF]/25 bg-[#D8DADF]/10 px-2 py-1 text-[10px] text-[#F8FAFC]"><Star size={11} />Hauptkontakt</span> : <StatusPill status="draft" />}</td>
            <td className="px-4 py-3.5">
              {contact.email && (
                <AddToMailingButton recipient={{ kind: "contact", id: contact.id, name: contactName(contact), email: contact.email }} />
              )}
            </td>
          </tr>
        ))}
      </DataTable>
      <p className="mt-3 text-xs text-[#8a9095]">{filtered.length} von {contacts.length} Kontakten</p>
    </>
  );
}
