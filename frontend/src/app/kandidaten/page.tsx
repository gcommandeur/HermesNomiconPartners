import { PageHeader } from "@/components/crm/page-header";
import { CandidatesTable } from "@/components/crm/candidates-table";
import { ImportWizard } from "@/components/crm/import-wizard";
import { CandidateCreateModal } from "@/components/crm/candidate-create-modal";

// Kein serverseitiger Datenfetch mehr hier: Next.js fuehrt Server Components
// bei jeder Navigation neu aus, ein "await getCandidates()" haette also bei
// jedem Seitenbesuch alle ~2900 Kandidaten neu vom Backend geholt - selbst
// mit Client-Cache (SWR) daneben. CandidatesTable laedt die Daten deshalb
// komplett client-seitig per SWR (siehe lib/api/hooks.ts); ein wiederholter
// Besuch derselben Session liest dann echt aus dem Cache statt neu zu fetchen.
export default function CandidatesPage() {
  return (
    <>
      <PageHeader eyebrow="Talent Pool" title="Kandidaten" action={<div className="flex flex-wrap gap-2"><ImportWizard entity="candidates" label="Kandidaten" /><CandidateCreateModal /></div>} />
      <CandidatesTable />
    </>
  );
}
