import { PageHeader } from "@/components/crm/page-header";
import { ClientsTable } from "@/components/crm/clients-table";
import { ImportWizard } from "@/components/crm/import-wizard";
import { ClientCreateModal } from "@/components/crm/client-create-modal";

// Kein serverseitiger Datenfetch mehr - gleiches Muster wie /kandidaten
// (siehe lib/api/hooks.ts): ClientsTable laedt komplett client-seitig per
// SWR, damit wiederholte Navigation aus dem Cache bedient wird statt bei
// jedem Besuch alle Kunden neu vom Backend zu holen.
export default function ClientsPage() {
  return (
    <>
      <PageHeader eyebrow="Client Intelligence" title="Kunden" action={<div className="flex flex-wrap gap-2"><ImportWizard entity="clients" label="Kunden" /><ClientCreateModal /></div>} />
      <ClientsTable />
    </>
  );
}
