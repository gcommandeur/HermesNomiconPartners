// NOMICON: Arbeitnehmerüberlassung - Einsätze.
import { PageHeader } from "@/components/crm/page-header";
import { StaffingAssignmentCreateButton } from "@/components/crm/staffing-assignment-create-modal";
import { StaffingAssignmentsView } from "@/components/crm/staffing-assignments-view";

export default async function StaffingAssignmentsPage({ searchParams }: { searchParams: Promise<{ ueberfaellig?: string }> }) {
  const { ueberfaellig } = await searchParams; // Link der Warnzeile in der Übersicht: ?ueberfaellig=1
  return (
    <>
      <PageHeader eyebrow="Überlassung" title="Einsätze" action={<StaffingAssignmentCreateButton />} />
      <StaffingAssignmentsView initialOverdue={ueberfaellig === "1"} />
    </>
  );
}
