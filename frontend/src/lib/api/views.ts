// NOMICON: Ansichten (Direct, Überlassung, Gesamt) - nur in der Nomicon-Kopie.
// Plain-Modul (kein "use client"): aus Server- und Client-Komponenten nutzbar.
import { apiGet, apiPut } from "./client";
import type { components } from "./schema";
import type { DataResult } from "./types";

type Schemas = components["schemas"];

export type ViewKey = Schemas["MyViewsRead"]["views"][number];
export type MyViews = Schemas["MyViewsRead"];
export type UserViews = Schemas["UserViewsRead"];

export const VIEW_LABELS: Record<ViewKey, string> = {
  direct: "Direct",
  staffing: "Überlassung",
  management: "Gesamt",
};

export const VIEW_DESCRIPTIONS: Record<ViewKey, string> = {
  direct: "Prozesse, Vakanzen, Sourcing, Fee",
  staffing: "Einsätze, Leiharbeitnehmer, Fristen, Stundenzettel, Abrechnung",
  management: "Rohertrag, Prognose, Provisionsmodell (nur Admins)",
};

/** Startseite je Ansicht (beim Umschalten). */
export const VIEW_HOME: Record<ViewKey, string> = {
  direct: "/prozesse",
  staffing: "/ueberlassung",
  management: "/geschaeftsfuehrung",
};

/** Welche Ansicht eine Seite exklusiv gehört; neutrale Seiten (Kandidaten, Kanzleien ...) gehören keiner. */
export function viewForPath(pathname: string): ViewKey | null {
  const startsWith = (prefix: string) => pathname === prefix || pathname.startsWith(`${prefix}/`);
  if (["/prozesse", "/vakanzen", "/sourcing", "/gewaehrleistung", "/prioritaet"].some(startsWith)) return "direct";
  if (startsWith("/ueberlassung")) return "staffing";
  if (startsWith("/geschaeftsfuehrung")) return "management";
  return null;
}

// Demo-Modus (ohne Backend): alle Ansichten, wie ein Admin.
const DEMO_MY_VIEWS: MyViews = { views: ["direct", "staffing", "management"], default_view: "management" };
const DEMO_USER_VIEWS: UserViews[] = [
  { user_id: "demo-admin", email: "demo-admin@nomicon.local", display_name: "Demo Admin", role: "admin", is_active: true, views: ["direct", "staffing", "management"], default_view: "management" },
  { user_id: "demo-vermittler", email: "demo-vermittler@nomicon.local", display_name: "Demo Vermittler", role: "member", is_active: true, views: ["direct"], default_view: "direct" },
];

export function getMyViews(): Promise<DataResult<MyViews>> {
  return apiGet<MyViews>("/me/views", DEMO_MY_VIEWS);
}

export function selectMyView(view: ViewKey): Promise<MyViews> {
  return apiPut<MyViews>("/me/view", { view });
}

export function getViewAccess(): Promise<DataResult<UserViews[]>> {
  return apiGet<UserViews[]>("/admin/view-access", DEMO_USER_VIEWS);
}

export function saveUserViews(userId: string, body: { views: ViewKey[]; default_view?: ViewKey | null }): Promise<UserViews> {
  return apiPut<UserViews>(`/admin/users/${userId}/views`, body);
}

export function getViewDefaults(): Promise<DataResult<{ views: ViewKey[] }>> {
  return apiGet<{ views: ViewKey[] }>("/admin/view-access/defaults", { views: ["direct"] });
}

export function saveViewDefaults(views: ViewKey[]): Promise<{ views: ViewKey[] }> {
  return apiPut<{ views: ViewKey[] }>("/admin/view-access/defaults", { views });
}

/** Server-Komponenten: darf der Nutzer Prozesse laden (Ansicht Direct)? Ohne Freigabe antworten
 * die Direct-Routen mit 403 - neutrale Seiten (Kandidat, Kanzlei) fragen dann gar nicht erst an. */
export async function hasView(view: ViewKey): Promise<boolean> {
  const { data } = await getMyViews();
  return data.views.includes(view);
}

/** Leeres Ergebnis für Abfragen, die mangels Freigabe nicht gestellt werden. */
export function noData<T>(data: T): DataResult<T> {
  return { data, source: "api" };
}
