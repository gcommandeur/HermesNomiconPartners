// NOMICON: Arbeitnehmerüberlassung - gemeinsamer Kopf mit Reiter-Leiste für alle Seiten darunter.
// Die Ansicht "Überlassung" muss freigeschaltet sein (sonst Seite "Keine Freigabe").
import { StaffingSubNav } from "@/components/crm/staffing-ui";
import { ViewGuard } from "@/components/crm/view-guard";

export default function StaffingLayout({ children }: { children: React.ReactNode }) {
  return (
    <ViewGuard view="staffing">
      <StaffingSubNav />
      {children}
    </ViewGuard>
  );
}
