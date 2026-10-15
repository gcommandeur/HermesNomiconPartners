import { ContactsTable } from "@/components/crm/contacts-table";
import { ContactCreateModal } from "@/components/crm/contact-create-modal";
import { PageHeader } from "@/components/crm/page-header";

// Kein serverseitiger Datenfetch mehr - gleiches Muster wie /kandidaten und
// /kunden (siehe lib/api/hooks.ts): ContactsTable laedt Kontakte UND
// Kunden komplett client-seitig per SWR (dieselben Cache-Keys wie die
// Kunden-Seite, daher meist schon warm).
export default function ContactsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Kunden-Beziehungsnetz"
        title="Kontakte"
        action={<ContactCreateModal />}
      />
      <ContactsTable />
    </>
  );
}
