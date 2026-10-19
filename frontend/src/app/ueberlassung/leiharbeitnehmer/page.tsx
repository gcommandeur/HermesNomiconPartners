// NOMICON: Arbeitnehmerüberlassung - die eigene Personenliste "Leiharbeitnehmer" gibt es nicht mehr.
// Leiharbeitnehmer sind Kandidaten: alte Lesezeichen führen auf die Kandidatenliste mit dem Überlassungsfilter.
import { redirect } from "next/navigation";
import { STAFFING_CANDIDATES_LIST } from "@/lib/staffing-candidate";

export default function StaffingWorkersRedirectPage() {
  redirect(STAFFING_CANDIDATES_LIST);
}
