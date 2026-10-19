// NOMICON: Arbeitnehmerüberlassung - Abrechnung.
import { PageHeader } from "@/components/crm/page-header";
import { StaffingBillingView } from "@/components/crm/staffing-billing-view";

export default function StaffingBillingPage() {
  return (
    <>
      <PageHeader eyebrow="Überlassung" title="Abrechnung" />
      <StaffingBillingView />
    </>
  );
}
