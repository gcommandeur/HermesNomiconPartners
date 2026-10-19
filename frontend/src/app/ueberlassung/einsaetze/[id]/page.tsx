// NOMICON: Arbeitnehmerüberlassung - Einsatz im Detail.
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { StaffingAssignmentDetailView } from "@/components/crm/staffing-assignment-detail";

export default async function StaffingAssignmentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <Link href="/ueberlassung/einsaetze" className="mb-5 inline-flex items-center gap-2 text-xs text-brand-muted hover:text-brand-platinum">
        <ArrowLeft size={14} />Zu den Einsätzen
      </Link>
      <StaffingAssignmentDetailView id={id} />
    </>
  );
}
