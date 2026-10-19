"use client";

// NOMICON: Ansichten - SWR-Hooks.
import { usePathname } from "next/navigation";
import useSWR, { mutate } from "swr";
import { getMyViews, getViewAccess, getViewDefaults, viewForPath, type ViewKey } from "./views";

const config = { revalidateOnFocus: true, dedupingInterval: 5_000 } as const;

export function useMyViews() {
  return useSWR("/me/views", getMyViews, config);
}

export function useViewAccess(enabled: boolean) {
  return useSWR(enabled ? "/admin/view-access" : null, getViewAccess, config);
}

export function useViewDefaults(enabled: boolean) {
  return useSWR(enabled ? "/admin/view-access/defaults" : null, getViewDefaults, config);
}

export function refreshViews() {
  return Promise.all([mutate("/me/views"), mutate("/admin/view-access"), mutate("/admin/view-access/defaults")]);
}

/** Aktive Ansicht: gehört die Seite genau einer freigeschalteten Ansicht, gilt diese; sonst die
 * gemerkte Auswahl des Nutzers. `null`, solange die Freigaben noch laden. */
export function useActiveView(): { views: ViewKey[]; active: ViewKey | null } {
  const pathname = usePathname();
  const { data } = useMyViews();
  if (!data) return { views: [], active: null };
  const { views, default_view: selected } = data.data;
  const byPath = viewForPath(pathname);
  return { views, active: byPath && views.includes(byPath) ? byPath : selected };
}
