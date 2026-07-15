import { redirect } from "next/navigation";

// Eigene Reaktivierungsliste entfernt (Phase L.2) - der "Erneut kontaktieren"-
// Filter auf /kandidaten (Phase K.3) deckt dieselbe Funktion ab. Alte Links/
// Bookmarks auf /reaktivierung landen deshalb dort mit aktivem Filter statt
// auf einer 404-Seite.
export default function ReactivationRedirectPage() {
  redirect("/kandidaten?reaktivierung=1");
}
