// NOMICON: Ansicht "Direct" muss freigeschaltet sein (sonst Seite "Keine Freigabe").
import { ViewGuard } from "@/components/crm/view-guard";

export default function DirectViewLayout({ children }: { children: React.ReactNode }) {
  return <ViewGuard view="direct">{children}</ViewGuard>;
}
