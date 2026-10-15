"use client";

import { useMemo } from "react";
import { Star } from "lucide-react";
import { FilterBar } from "@/components/crm/filter-bar";
import { DataTable } from "@/components/crm/data-table";
import { StatusPill } from "@/components/crm/status-pill";
import { ExportActions } from "@/components/crm/export-actions";
import { DemoNotice } from "@/components/crm/demo-notice";
import { ErrorState } from "@/components/crm/error-state";
import { ListSkeleton } from "@/components/crm/list-skeleton";
import { PaginationControls } from "@/components/crm/pagination-controls";
import { AddToMailingButton } from "@/components/crm/add-to-mailing-button";
import { MailComposeButton } from "@/components/crm/mail-compose-modal";
import { contactName } from "@/lib/utils";
import { useServerSearchList } from "@/lib/api/use-server-search";
import { getContactsPage } from "@/lib/api/queries";
import type { Contact } from "@/lib/api/types";

export function ContactsTable() {
  // Serverseitige Suche + Pagination (siehe lib/api/use-server-search.ts) -
  // der Kundenname kommt bereits vom Backend denormalisiert mit
  // (client_company_name, Join gegen client_companies) - das Frontend muss
  // dafuer nicht mehr den kompletten Kunden-Bestand separat laden.
  const {
    search,
    setSearch,
    page,
    setPage,
    pageCount,
    items: contacts,
    totalCount,
    hasLoadedOnce,
    isValidating,
    error,
    source,
    demoError,
    retry,
  } = useServerSearchList<Contact>("/contacts", getContactsPage);

  const exportRows = useMemo(() => contacts.map((contact) => ({
    Name: contactName(contact),
    Kunde: contact.client_company_name ?? "Kunde",
    Rolle: contact.role_title,
    Email: contact.email,
    Telefon: contact.phone,
    Hauptkontakt: contact.is_primary ? "Ja" : "Nein",
  })), [contacts]);

  if (error) {
    return <ErrorState onRetry={() => void retry()} />;
  }

  // Skeleton NUR beim allerersten Laden - siehe list-skeleton.tsx, warum
  // hier NICHT SWRs `isLoading` verwendet werden darf (Fokusverlust im
  // Suchfeld bei jedem Tastendruck).
  if (!hasLoadedOnce) {
    return <ListSkeleton />;
  }

  return (
    <>
      <div className="mb-4 flex justify-end"><ExportActions filename="kontakte" rows={exportRows} /></div>
      <DemoNotice source={source ?? "api"} error={demoError} />
      <FilterBar
        placeholder="Nach Name, Kunde oder Rolle suchen"
        value={search}
        onChange={setSearch}
        loading={isValidating}
      />
      {/* Mobile (<lg): Karten statt der 7-spaltigen Desktop-Tabelle, siehe
       * candidates-table.tsx fuer denselben Fix + Begruendung (Nutzer-
       * Feedback "mobile Version nicht passend"). */}
      <div className="space-y-2 lg:hidden">
        {contacts.map((contact) => (
          <div key={contact.id} className="rounded-lg border border-white/10 bg-brand-panel p-3">
            <div className="flex items-start justify-between gap-2">
              <p className="min-w-0 truncate text-sm font-semibold text-brand-platinum">{contactName(contact)}</p>
              {contact.is_primary ? (
                <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-brand-platinum/25 bg-brand-platinum/10 px-2 py-1 text-[9.5px] text-brand-text"><Star size={11} />Hauptkontakt</span>
              ) : (
                <StatusPill status="draft" />
              )}
            </div>
            <p className="mt-0.5 truncate text-xs text-brand-muted">
              {contact.client_company_name ?? "Kunde"}{contact.role_title ? ` · ${contact.role_title}` : ""}
            </p>
            <div className="mt-2 flex items-center justify-between gap-2 text-[10.45px] text-brand-gray">
              <span className="min-w-0 truncate">{contact.email ?? "—"} {contact.phone ? `· ${contact.phone}` : ""}</span>
              {contact.email && (
                <div className="flex shrink-0 items-center gap-1.5">
                  <AddToMailingButton recipient={{ kind: "contact", id: contact.id, name: contactName(contact), email: contact.email }} />
                  <MailComposeButton
                    toAddress={contact.email}
                    toName={contactName(contact)}
                    contactPersonId={contact.id}
                    clientCompanyId={contact.client_company_id}
                    placeholderValues={{ contact: contactName(contact), client: contact.client_company_name ?? "" }}
                    label="Mail"
                  />
                </div>
              )}
            </div>
          </div>
        ))}
        {contacts.length === 0 && (
          <p className="py-8 text-center text-xs text-brand-muted">Keine Kontakte gefunden.</p>
        )}
      </div>
      <div className="hidden lg:block">
      <DataTable headers={["Kontakt", "Kunde", "Rolle", "E-Mail", "Telefon", "Hauptkontakt", "Mailing"]}>
        {contacts.map((contact) => (
          <tr key={contact.id} className="hover:bg-brand-hover/35">
            <td className="px-4 py-3.5 font-semibold text-brand-platinum">{contactName(contact)}</td>
            <td className="px-4 py-3.5">{contact.client_company_name ?? "Kunde"}</td>
            <td className="px-4 py-3.5">{contact.role_title ?? "—"}</td>
            <td className="px-4 py-3.5">{contact.email ?? "—"}</td>
            <td className="px-4 py-3.5">{contact.phone ?? "—"}</td>
            <td className="px-4 py-3.5">{contact.is_primary ? <span className="inline-flex items-center gap-1 rounded-full border border-brand-platinum/25 bg-brand-platinum/10 px-2 py-1 text-[9.5px] text-brand-text"><Star size={11} />Hauptkontakt</span> : <StatusPill status="draft" />}</td>
            <td className="px-4 py-3.5">
              {contact.email && (
                <div className="flex items-center gap-1.5">
                  <AddToMailingButton recipient={{ kind: "contact", id: contact.id, name: contactName(contact), email: contact.email }} />
                  <MailComposeButton
                    toAddress={contact.email}
                    toName={contactName(contact)}
                    contactPersonId={contact.id}
                    clientCompanyId={contact.client_company_id}
                    placeholderValues={{ contact: contactName(contact), client: contact.client_company_name ?? "" }}
                    label="Mail"
                  />
                </div>
              )}
            </td>
          </tr>
        ))}
      </DataTable>
      </div>
      <PaginationControls page={page} pageCount={pageCount} onChange={setPage} />
      <p className="mt-3 text-xs text-brand-gray">{contacts.length} von {totalCount} Kontakten</p>
    </>
  );
}
