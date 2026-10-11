// NOMICON: Arbeitnehmerüberlassung - Compliance.
import { PageHeader } from "@/components/crm/page-header";
import { StaffingComplianceView } from "@/components/crm/staffing-compliance-view";

export default function StaffingCompliancePage() {
  return (
    <>
      <PageHeader eyebrow="Überlassung" title="Compliance" />
      <StaffingComplianceView />
    </>
  );
}
