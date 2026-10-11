// NOMICON: Arbeitnehmerüberlassung - gemeinsamer Kopf mit Reiter-Leiste für alle Seiten darunter.
import { StaffingSubNav } from "@/components/crm/staffing-ui";

export default function StaffingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <StaffingSubNav />
      {children}
    </>
  );
}
