import {
  BarChart3,
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  ClipboardCheck,
  ContactRound,
  CalendarRange, // NOMICON
  HardHat, // NOMICON
  Receipt, // NOMICON
  Wallet, // NOMICON
  KanbanSquare,
  UserRoundSearch,
  LayoutDashboard,
  Mail,
  Map,
  Settings,
  ShieldCheck,
  Sparkles,
  Trophy,
  Users,
} from "lucide-react";

import type { ViewKey } from "@/lib/api/views"; // NOMICON

export type NavigationItem = {
  label: string;
  href: string;
  icon: typeof LayoutDashboard;
  adminOnly?: boolean;
  /** Auch fuer Teamleiter sichtbar (Server begrenzt auf das Team). */
  teamLeadToo?: boolean;
  /** Zusaetzliche Pfade, bei denen der Eintrag als aktiv gilt. */
  alsoActiveFor?: string[];
  /** Pfade, bei denen der Eintrag trotz passendem Praefix NICHT aktiv ist. */
  notActiveFor?: string[];
  /** Zaehler-Badge (Daten holt die Seitenleiste). */
  badge?: "approvals" | "aiProposals";
  /** Nur zeigen, wenn die Claude-Schnittstelle eingeschaltet ist. */
  requiresAi?: boolean;
  /** NOMICON: Nur in diesen Ansichten zeigen (ohne Angabe: in jeder Ansicht). */
  views?: ViewKey[];
  /** NOMICON: Abweichendes Linkziel je Ansicht (z. B. vorausgewählter Filter); die Aktiv-Erkennung bleibt `href`. */
  viewHrefs?: Partial<Record<ViewKey, string>>;
};

export type NavigationGroup = {
  id: string;
  label: string;
  /** Ganze Gruppe nur fuer Admins. */
  adminOnly?: boolean;
  /** NOMICON: Abweichende Überschrift je Ansicht (Überlassung: "Überlassung" statt "Recruiting"). */
  viewLabels?: Partial<Record<ViewKey, string>>;
  items: NavigationItem[];
};

/** Seiten unter /einstellungen, die zum Bereich "Administration" gehoeren
 * (Kachel-Seite /einstellungen/administration). Der Eintrag "Administration"
 * ist fuer sie aktiv, "Einstellungen" (nur Persoenliches) nicht. */
export const ADMINISTRATION_PATHS = [
  "/einstellungen/administration",
  "/einstellungen/nutzer",
  "/einstellungen/postfaecher",
  "/einstellungen/kpi-punkte",
  "/einstellungen/sequenzen",
  "/einstellungen/jobs",
  "/einstellungen/webhooks",
  "/einstellungen/felder",
  "/einstellungen/audit-log",
  "/einstellungen/loeschanfragen",
  "/einstellungen/vorstellungs-archiv",
  "/einstellungen/ansichten", // NOMICON
];

// Aufbau mit dem Nutzer abgestimmt (Arbeitsplan 2, Q2). Rechte (adminOnly /
// teamLeadToo) und Routen sind gegenueber der frueheren flachen Liste unveraendert.
export const navigationGroups: NavigationGroup[] = [
  {
    id: "schreibtisch",
    label: "Schreibtisch",
    items: [
      { label: "Übersicht", href: "/", icon: LayoutDashboard },
      { label: "Kalender", href: "/kalender", icon: CalendarDays },
      { label: "Mailing", href: "/mailing", icon: Mail },
      { label: "Meine Provision", href: "/provision", icon: Wallet }, // NOMICON
      { label: "Claude-Vorschläge", href: "/claude-vorschlaege", icon: Sparkles, badge: "aiProposals", requiresAi: true },
    ],
  },
  {
    id: "recruiting",
    label: "Recruiting",
    viewLabels: { staffing: "Überlassung" }, // NOMICON: in der Ansicht Überlassung stehen alle Punkte in einer Gruppe
    items: [
      // Eigener "Reaktivierung"-Menuepunkt entfernt (Phase L.2): der
      // "Erneut kontaktieren"-Filter auf /kandidaten deckt dieselbe Funktion ab.
      // In der Ansicht Überlassung führt "Kandidaten" auf die Liste mit vorausgewähltem Überlassungsfilter
      // (Leiharbeitnehmer sind Kandidaten, es gibt keine eigene Personenliste mehr).
      { label: "Kandidaten", href: "/kandidaten", icon: Users, viewHrefs: { staffing: "/kandidaten?ueberlassung=workers" } }, // NOMICON
      { label: "Prozesse", href: "/prozesse", icon: KanbanSquare, views: ["direct"] }, // NOMICON
      { label: "Vakanzen", href: "/vakanzen", icon: BriefcaseBusiness, views: ["direct"] }, // NOMICON
      // Review-Ebene des Sourcing-Agents: gefundene Personen werden hier
      // bestaetigt/verworfen, bevor sie Kandidaten werden.
      { label: "Sourcing", href: "/sourcing", icon: UserRoundSearch, views: ["direct"] }, // NOMICON
      // NOMICON: Arbeitnehmerüberlassung (nur Ansicht Überlassung), gleiche Gruppe wie die Kandidaten
      { label: "Übersicht & Fristen", href: "/ueberlassung", icon: HardHat, views: ["staffing"], notActiveFor: ["/ueberlassung/einsaetze", "/ueberlassung/leiharbeitnehmer", "/ueberlassung/abrechnung", "/ueberlassung/compliance"] },
      { label: "Einsätze", href: "/ueberlassung/einsaetze", icon: CalendarRange, views: ["staffing"] },
      { label: "Abrechnung", href: "/ueberlassung/abrechnung", icon: Receipt, views: ["staffing"] },
      { label: "Compliance", href: "/ueberlassung/compliance", icon: ShieldCheck, adminOnly: true, teamLeadToo: true, views: ["staffing"] }, // Vermittler: Meldungen statt Seite
    ],
  },
  {
    id: "kunden",
    label: "Kunden",
    items: [
      { label: "Kunden", href: "/kunden", icon: Building2 },
      { label: "Kontakte", href: "/kontakte", icon: ContactRound },
      { label: "Geo Mapping", href: "/geo-mapping", icon: Map },
    ],
  },
  {
    id: "management",
    label: "Management",
    items: [
      { label: "Analytics", href: "/analytics", icon: BarChart3 },
      { label: "Geschäftsführung", href: "/geschaeftsfuehrung", icon: Trophy, adminOnly: true, teamLeadToo: true, views: ["management", "direct"] }, // NOMICON: Gesamt (Admins); Teamleiter sehen die Team-Kennzahlen unter Direct
    ],
  },
  {
    id: "administration",
    label: "Administration",
    adminOnly: true,
    items: [
      { label: "Freigaben", href: "/freigaben", icon: ClipboardCheck, adminOnly: true, badge: "approvals" },
      {
        label: "Administration",
        href: "/einstellungen/administration",
        icon: ShieldCheck,
        adminOnly: true,
        alsoActiveFor: ADMINISTRATION_PATHS,
      },
    ],
  },
];

/** Flache Liste aller Gruppen-Eintraege (Kompatibilitaet, z. B. fuer Suche). */
export const primaryNavigation: NavigationItem[] = navigationGroups.flatMap((group) => group.items);

export const utilityNavigation: NavigationItem[] = [
  // Nur Persoenliches (Kalender-Feed, Outlook/Postfach); die Verwaltung
  // liegt unter "Administration".
  { label: "Einstellungen", href: "/einstellungen", icon: Settings, notActiveFor: ADMINISTRATION_PATHS },
];

export const navigation = [...primaryNavigation, ...utilityNavigation];

/** Ob ein Eintrag zum aktuellen Pfad gehoert. */
export function isNavigationItemActive(item: NavigationItem, pathname: string): boolean {
  const matches = (prefix: string) => pathname === prefix || pathname.startsWith(`${prefix}/`);
  if (item.notActiveFor?.some(matches)) return false;
  if (item.alsoActiveFor?.some(matches)) return true;
  return item.href === "/" ? pathname === "/" : matches(item.href);
}

/** Welche Eintraege der Nutzer sehen darf. */
export function visibleItems(
  items: NavigationItem[],
  isAdmin: boolean,
  isTeamLead: boolean,
): NavigationItem[] {
  return items.filter((item) => !item.adminOnly || isAdmin || (item.teamLeadToo && isTeamLead));
}

/** NOMICON: Welche Einträge in der gewählten Ansicht erscheinen. Solange die Freigaben laden
 * (`active === null`), nur Einträge ohne Ansichtsbindung. */
export function inActiveView(items: NavigationItem[], active: ViewKey | null): NavigationItem[] {
  return items.filter((item) => !item.views || (active !== null && item.views.includes(active)));
}
