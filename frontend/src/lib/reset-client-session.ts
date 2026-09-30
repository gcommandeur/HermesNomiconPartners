"use client";

import { mutate } from "swr";
import { clearRecentCandidates } from "@/lib/recent-candidates";

/** Verwirft alles, was im Browser noch vom vorherigen Nutzer stammt - bei
 * Login und Logout, damit nach einem Nutzerwechsel im selben Tab (ohne
 * Hard-Reload) keine fremden Daten sichtbar bleiben. router.refresh() allein
 * erreicht weder den SWR-Cache noch den localStorage-Verlauf. */
export async function resetClientSession() {
  clearRecentCandidates();
  await mutate(() => true, undefined, { revalidate: false });
}
