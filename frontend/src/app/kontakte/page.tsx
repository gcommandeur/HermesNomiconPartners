import { ContactsTable } from "@/components/crm/contacts-table";
import { ContactCreateModal } from "@/components/crm/contact-create-modal";
import { PageHeader } from "@/components/crm/page-header";

// Kein serverseitiger Datenfetch mehr - gleiches Muster wie /kandidaten und
// /kanzleien (siehe lib/api/hooks.ts): ContactsTable laedt Kontakte UND
// Kanzleien komplett client-seitig per SWR (dieselben Cache-Keys wie die
// Kanzleien-Seite, daher meist schon warm).
export default function ContactsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Kanzlei-Beziehungsnetz"
        title="Kontakte"
        action={<ContactCreateModal />}
      />
      <ContactsTable />
    </>
  );
}
