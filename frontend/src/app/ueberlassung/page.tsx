// NOMICON: Arbeitnehmerüberlassung - Übersicht.
import { PageHeader } from "@/components/crm/page-header";
import { StaffingOverviewView } from "@/components/crm/staffing-overview-view";

export default function StaffingOverviewPage() {
  return (
    <>
      <PageHeader eyebrow="Überlassung" title="Übersicht" />
      <StaffingOverviewView />
    </>
  );
}
