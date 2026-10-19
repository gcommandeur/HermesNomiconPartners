// NOMICON: Arbeitnehmerüberlassung - die Detailseite des Leiharbeitnehmers ist jetzt der Reiter "Überlassung"
// am Kandidatenprofil. Alte Adressen (Board, Aufgaben, Meldungen, Lesezeichen) leiten dorthin weiter.
import { redirect } from "next/navigation";
import { getStaffingWorker } from "@/lib/api/staffing";
import { workerRedirectTarget } from "@/lib/staffing-candidate";

export default async function StaffingWorkerRedirectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let worker = null;
  try {
    worker = (await getStaffingWorker(id)).data;
  } catch {
    worker = null; // nicht vorhanden oder nicht erreichbar: Liste statt Fehlerseite
  }
  redirect(workerRedirectTarget(worker));
}
