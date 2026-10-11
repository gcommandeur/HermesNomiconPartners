// NOMICON: Arbeitnehmerüberlassung - Leiharbeitnehmer.
import { PageHeader } from "@/components/crm/page-header";
import { StaffingWorkerCreateButton, StaffingWorkersView } from "@/components/crm/staffing-workers-view";

export default function StaffingWorkersPage() {
  return (
    <>
      <PageHeader eyebrow="Überlassung" title="Leiharbeitnehmer" action={<StaffingWorkerCreateButton />} />
      <StaffingWorkersView />
    </>
  );
}
