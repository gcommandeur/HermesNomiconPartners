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
  Trophy,
  Users,
} from "lucide-react";

export const primaryNavigation: {
  label: string;
  href: string;
  icon: typeof LayoutDashboard;
  adminOnly?: boolean;
}[] = [
  { label: "Übersicht", href: "/", icon: LayoutDashboard },
  // Eigener "Reaktivierung"-Menuepunkt entfernt (Phase L.2): der
  // "Erneut kontaktieren"-Filter auf /kandidaten (Phase K.3) deckt dieselbe
  // Funktion ab, /reaktivierung als Route wurde ebenfalls entfernt.
  { label: "Kandidaten", href: "/kandidaten", icon: Users },
  // Review-Ebene des Sourcing-Agents: gefundene Personen werden hier
  // bestaetigt/verworfen, bevor sie Kandidaten werden (siehe /sourcing).
  { label: "Sourcing", href: "/sourcing", icon: UserRoundSearch },
  { label: "Kanzleien", href: "/kanzleien", icon: Building2 },
  { label: "Kontakte", href: "/kontakte", icon: ContactRound },
  { label: "Prozesse", href: "/prozesse", icon: KanbanSquare },
  { label: "Kalender", href: "/kalender", icon: CalendarDays },
  { label: "Vakanzen", href: "/vakanzen", icon: BriefcaseBusiness },
  { label: "Geo Mapping", href: "/geo-mapping", icon: Map },
  { label: "Mailing", href: "/mailing", icon: Mail },
  { label: "Analytics", href: "/analytics", icon: BarChart3 },
  // Nur fuer Admins sichtbar (siehe sidebar.tsx) - gleiche Sichtbarkeits-
  // logik wie der Administration-Block in einstellungen/page.tsx.
  { label: "Geschäftsführung", href: "/geschaeftsfuehrung", icon: Trophy, adminOnly: true },
  { label: "Freigaben", href: "/freigaben", icon: ClipboardCheck, adminOnly: true },
];

export const utilityNavigation = [
  { label: "Einstellungen", href: "/einstellungen", icon: Settings },
];

export const navigation = [...primaryNavigation, ...utilityNavigation];
