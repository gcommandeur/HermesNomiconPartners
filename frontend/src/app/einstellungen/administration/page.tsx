"use client";

import Link from "next/link";
import {
  Archive,
  Boxes,
  ClipboardList,
  KeyRound,
  Layers, // NOMICON
  Mail,
  Send,
  Sparkles,
  ShieldOff,
  SlidersHorizontal,
  Timer,
  Trash2,
  Trophy,
  Users,
  Webhook,
} from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { useCurrentUser } from "@/lib/api/hooks";
import { brand } from "@/lib/brand";

type Tile = { href: string; label: string; description: string; icon: typeof Users };

// Gruppen wie in der Seitenleiste abgestimmt (Arbeitsplan 2, Q2). Neue
// Verwaltungsseiten hier eintragen UND in ADMINISTRATION_PATHS
// (components/layout/navigation.ts), damit die Seitenleiste aktiv markiert.
const GROUPS: { title: string; icon: typeof Users; tiles: Tile[] }[] = [
  {
    title: "Team und Zugänge",
    icon: KeyRound,
    tiles: [
      { href: "/einstellungen/nutzer", label: "Nutzerverwaltung", description: "Konten, Rollen und Teamleiter-Zuordnung.", icon: Users },
      { href: "/einstellungen/postfaecher", label: "E-Mails & Konten", description: "Gemeinsame Postfächer und Outlook-Verbindungen.", icon: Mail },
      { href: "/einstellungen/kpi-punkte", label: "KPI-Punkte", description: "Punkteregeln für das Ranking.", icon: Trophy },
      { href: "/einstellungen/ansichten", label: "Ansichten", description: "Direct, Überlassung und Gesamt je Mitarbeiter freischalten.", icon: Layers }, // NOMICON
    ],
  },
  {
    title: "Automatisierung",
    icon: Timer,
    tiles: [
      { href: "/einstellungen/sequenzen", label: "Outreach-Sequenzen", description: "Mehrstufige Kontaktfolgen für Kandidaten.", icon: Send },
      { href: "/einstellungen/jobs", label: "Hintergrundjobs", description: "Laufende und fehlgeschlagene Jobs, Neustart.", icon: Boxes },
      { href: "/einstellungen/webhooks", label: "Webhooks", description: "Ereignisse signiert an andere Systeme melden.", icon: Webhook },
    ],
  },
  {
    title: "Daten und Compliance",
    icon: SlidersHorizontal,
    tiles: [
      { href: "/einstellungen/felder", label: "Eigene Felder", description: "Zusatzfelder für Kandidaten, Kunden und Kontakte.", icon: SlidersHorizontal },
      { href: "/claude-vorschlaege", label: "Claude-Vorschläge", description: "Vorschläge der Claude-Schnittstelle prüfen und freigeben.", icon: Sparkles },
      { href: "/einstellungen/audit-log", label: "Audit-Log", description: "Wer hat wann was geändert.", icon: ClipboardList },
      { href: "/einstellungen/loeschanfragen", label: "Löschanfragen", description: "Datenschutz: Löschungen prüfen und ausführen.", icon: Trash2 },
      { href: "/einstellungen/vorstellungs-archiv", label: "Vorstellungs-Archiv", description: "Nachweis für Honorar-Streitfälle: was an der Kunde ging.", icon: Archive },
    ],
  },
];

export default function AdministrationPage() {
  const { data: meData, isLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;

  if (isLoading) {
    return <div className="h-16 animate-pulse rounded-lg bg-brand-surface" />;
  }

  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow="Administration" title="Administration" />
        <Card>
          <CardContent className="flex items-center gap-3 text-sm text-brand-muted">
            <ShieldOff size={18} /> Nur für Admins zugänglich.
          </CardContent>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader eyebrow={brand.appName} title="Administration" />
      <div className="space-y-8">
        {GROUPS.map((group) => (
          <section key={group.title}>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-brand-platinum">
              <group.icon size={15} className="text-brand-accent-light" /> {group.title}
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {group.tiles.map((tile) => (
                <Link key={tile.href} href={tile.href} className="group block">
                  <Card className="h-full transition-colors group-hover:border-brand-accent/60">
                    <CardContent className="flex items-start gap-3">
                      <tile.icon size={18} className="mt-0.5 shrink-0 text-brand-accent-light" />
                      <div>
                        <p className="font-medium text-brand-text">{tile.label}</p>
                        <p className="mt-1 text-xs text-brand-muted">{tile.description}</p>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
