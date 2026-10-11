// NOMICON: Arbeitnehmerüberlassung - Einsätze.
import { PageHeader } from "@/components/crm/page-header";
import { StaffingAssignmentCreateButton } from "@/components/crm/staffing-assignment-create-modal";
import { StaffingAssignmentsView } from "@/components/crm/staffing-assignments-view";

export default function StaffingAssignmentsPage() {
  return (
    <>
      <PageHeader eyebrow="Überlassung" title="Einsätze" action={<StaffingAssignmentCreateButton />} />
      <StaffingAssignmentsView />
    </>
  );
}
