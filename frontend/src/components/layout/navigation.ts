import {
  BarChart3,
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  ClipboardCheck,
  ContactRound,
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
};

export type NavigationGroup = {
  id: string;
  label: string;
  /** Ganze Gruppe nur fuer Admins. */
  adminOnly?: boolean;
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
      { label: "Claude-Vorschläge", href: "/claude-vorschlaege", icon: Sparkles, badge: "aiProposals", requiresAi: true },
    ],
  },
  {
    id: "recruiting",
    label: "Recruiting",
    items: [
      // Eigener "Reaktivierung"-Menuepunkt entfernt (Phase L.2): der
      // "Erneut kontaktieren"-Filter auf /kandidaten deckt dieselbe Funktion ab.
      { label: "Kandidaten", href: "/kandidaten", icon: Users },
      { label: "Prozesse", href: "/prozesse", icon: KanbanSquare },
      { label: "Vakanzen", href: "/vakanzen", icon: BriefcaseBusiness },
      // Review-Ebene des Sourcing-Agents: gefundene Personen werden hier
      // bestaetigt/verworfen, bevor sie Kandidaten werden.
      { label: "Sourcing", href: "/sourcing", icon: UserRoundSearch },
    ],
  },
  {
    id: "kunden",
    label: "Kunden",
    items: [
      { label: "Kanzleien", href: "/kanzleien", icon: Building2 },
      { label: "Kontakte", href: "/kontakte", icon: ContactRound },
      { label: "Geo Mapping", href: "/geo-mapping", icon: Map },
    ],
  },
  {
    id: "management",
    label: "Management",
    items: [
      { label: "Analytics", href: "/analytics", icon: BarChart3 },
      { label: "Geschäftsführung", href: "/geschaeftsfuehrung", icon: Trophy, adminOnly: true, teamLeadToo: true },
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
