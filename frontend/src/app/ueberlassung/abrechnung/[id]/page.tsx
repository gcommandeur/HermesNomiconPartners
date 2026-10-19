// NOMICON: Arbeitnehmerüberlassung - Rechnung im Detail.
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { StaffingInvoiceDetailView } from "@/components/crm/staffing-invoice-detail";

export default async function StaffingInvoicePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <>
      <Link href="/ueberlassung/abrechnung" className="mb-5 inline-flex items-center gap-2 text-xs text-brand-muted hover:text-brand-platinum">
        <ArrowLeft size={14} />Zur Abrechnung
      </Link>
      <StaffingInvoiceDetailView id={id} />
    </>
  );
}
