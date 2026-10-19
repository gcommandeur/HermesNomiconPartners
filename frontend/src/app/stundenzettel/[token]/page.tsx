// NOMICON: Freigabeseite für Kunden (ohne Login), erreichbar über den Link aus dem Stundenzettel.
import type { Metadata } from "next";
import { StaffingTimesheetApproval } from "@/components/crm/staffing-timesheet-approval";

// Der Token steht in der Adresse: nicht indexieren und die Adresse nie als Referrer weitergeben.
export const metadata: Metadata = {
  title: "Stundenzettel zur Freigabe",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export const dynamic = "force-dynamic";

export default async function TimesheetApprovalPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <StaffingTimesheetApproval token={token} />;
}
