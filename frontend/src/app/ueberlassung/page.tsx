// NOMICON: Arbeitnehmerüberlassung - Disposition (Übersicht).
import { PageHeader } from "@/components/crm/page-header";
import { StaffingDispositionView } from "@/components/crm/staffing-disposition-view";

export default function StaffingOverviewPage() {
  return (
    <>
      <PageHeader eyebrow="Überlassung" title="Disposition" />
      <StaffingDispositionView />
    </>
  );
}
