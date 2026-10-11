// NOMICON: Arbeitnehmerüberlassung - Leiharbeitnehmer im Detail.
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { StaffingWorkerDetailView } from "@/components/crm/staffing-workers-view";

export default async function StaffingWorkerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <Link href="/ueberlassung/leiharbeitnehmer" className="mb-5 inline-flex items-center gap-2 text-xs text-brand-muted hover:text-brand-platinum">
        <ArrowLeft size={14} />Zu den Leiharbeitnehmern
      </Link>
      <StaffingWorkerDetailView id={id} />
    </>
  );
}
