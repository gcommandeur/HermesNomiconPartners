// NOMICON: Arbeitnehmerüberlassung - Compliance.
import { PageHeader } from "@/components/crm/page-header";
import { StaffingComplianceGate } from "@/components/crm/staffing-compliance-gate";
import { StaffingComplianceView } from "@/components/crm/staffing-compliance-view";

export default function StaffingCompliancePage() {
  return (
    <>
      <PageHeader eyebrow="Überlassung" title="Compliance" />
      <StaffingComplianceGate>
        <StaffingComplianceView />
      </StaffingComplianceGate>
    </>
  );
}
