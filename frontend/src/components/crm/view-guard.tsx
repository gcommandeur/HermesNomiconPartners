// NOMICON: Ansichten - nur in der Nomicon-Kopie. Server-Komponente: prüft die Freigabe vor dem
// Rendern einer Seite (Layouts von /prozesse, /vakanzen, /sourcing, /ueberlassung).
import { NoAccess } from "./no-access";
import { getMyViews, VIEW_LABELS, type ViewKey } from "@/lib/api/views";

export async function ViewGuard({ view, children }: { view: ViewKey; children: React.ReactNode }) {
  const { data } = await getMyViews();
  if (!data.views.includes(view)) return <NoAccess viewLabel={VIEW_LABELS[view]} />;
  return <>{children}</>;
}
