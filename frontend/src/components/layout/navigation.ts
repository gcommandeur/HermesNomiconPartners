import {
  BarChart3,
  BriefcaseBusiness,
  Building2,
  ContactRound,
  KanbanSquare,
  LayoutDashboard,
  Mail,
  Map,
  Settings,
  Users,
} from "lucide-react";

export const primaryNavigation = [
  { label: "Übersicht", href: "/", icon: LayoutDashboard },
  // Eigener "Reaktivierung"-Menuepunkt entfernt (Phase L.2): der
  // "Erneut kontaktieren"-Filter auf /kandidaten (Phase K.3) deckt dieselbe
  // Funktion ab, /reaktivierung als Route wurde ebenfalls entfernt.
  { label: "Kandidaten", href: "/kandidaten", icon: Users },
  { label: "Kanzleien", href: "/kanzleien", icon: Building2 },
  { label: "Kontakte", href: "/kontakte", icon: ContactRound },
  { label: "Prozesse", href: "/prozesse", icon: KanbanSquare },
  { label: "Vakanzen", href: "/vakanzen", icon: BriefcaseBusiness },
  { label: "Geo Mapping", href: "/geo-mapping", icon: Map },
  { label: "Mailing", href: "/mailing", icon: Mail },
  { label: "Analytics", href: "/analytics", icon: BarChart3 },
];

export const utilityNavigation = [
  { label: "Einstellungen", href: "/einstellungen", icon: Settings },
];

export const navigation = [...primaryNavigation, ...utilityNavigation];
