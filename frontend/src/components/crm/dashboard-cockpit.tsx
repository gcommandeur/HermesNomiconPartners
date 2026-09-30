"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, CalendarClock, FileCheck2, Flame, Gauge, ReceiptText, Trophy, TimerReset } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/crm/page-header";
import { DemoNotice } from "@/components/crm/demo-notice";
import { WeeklyChartLoader } from "@/components/crm/weekly-chart-loader";
import { DashboardTodo } from "@/components/crm/dashboard-todo";
import { useCurrentUser, useKpiRankingCache } from "@/lib/api/hooks";
import { PITCH_LABEL, STAGE_LABELS } from "@/lib/stage-labels";
import { cn, formatCurrency, formatDate } from "@/lib/utils";
import type { Cockpit, CockpitItem, SubmissionStatus } from "@/lib/api/types";

function metricLabel(metric: string): string {
  if (metric === "points") return "Punkte";
  if (metric === "pitch") return PITCH_LABEL;
  return STAGE_LABELS[metric as keyof typeof STAGE_LABELS] ?? metric;
}

/** Live-Ranking-Widget (Auftrag "Geschaeftsfuehrer-Ansicht + KPI-Punkte-
 * System + Live-Ranking") - fuer ALLE Nutzer sichtbar, bewusst kein
 * Admin-Gate (Nutzer-Vorgabe: "Recruiter sollen sich untereinander sehen
 * koennen", das ist der Wettbewerbs-Gedanke). Tag/Woche ist ein rein
 * lokaler Toggle (kein Persistieren - Server-Default aus app_settings
 * greift bei jedem Neuladen wieder), die angezeigte METRIK bleibt die
 * admin-konfigurierte Voreinstellung (siehe /einstellungen/kpi-punkte). */
function LiveRankingCard() {
  const { data: meData } = useCurrentUser();
  const currentUserId = meData?.data.id;
  const [period, setPeriod] = useState<"day" | "week" | undefined>(undefined);
  const { data, isLoading } = useKpiRankingCache(period, undefined);
  const ranking = data?.data;
  const entries = ranking?.entries ?? [];

  return (
    <Card>
      <CardHeader>
        <div>
          <div className="flex items-center gap-2"><Trophy size={17} className="text-[#F0B429]" /><h2 className="font-semibold">Live-Ranking</h2></div>
          <p className="mt-1 text-xs text-[#94A3B8]">
            {ranking ? metricLabel(ranking.metric) : "Wird geladen…"} · {(period ?? ranking?.period) === "day" ? "heute" : "diese Woche"}
          </p>
        </div>
        <div className="flex gap-1.5">
          <Button size="sm" variant={(period ?? ranking?.period) === "day" ? "default" : "outline"} onClick={() => setPeriod("day")}>Tag</Button>
          <Button size="sm" variant={(period ?? ranking?.period) === "week" ? "default" : "outline"} onClick={() => setPeriod("week")}>Woche</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {isLoading && !ranking ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="h-10 animate-pulse rounded-lg bg-[#0D1B2E]" />
            ))}
          </div>
        ) : entries.length === 0 ? (
          <p className="py-6 text-center text-xs text-[#94A3B8]">Noch keine Daten für diesen Zeitraum.</p>
        ) : (
          entries.map((entry, index) => {
            const isSelf = entry.user_id === currentUserId;
            return (
              <div
                key={entry.user_id}
                className={cn(
                  "flex items-center gap-3 rounded-lg border p-2.5 text-xs",
                  isSelf ? "border-[#1F5FA8]/40 bg-[#153A66]/60" : "border-white/10 bg-[#0D1B2E]/75",
                )}
              >
                <span className="w-6 shrink-0 text-center font-semibold text-[#94A3B8]">{index + 1}</span>
                <span className={cn("min-w-0 flex-1 truncate", isSelf ? "font-semibold text-white" : "text-[#D8DADF]")}>
                  {entry.display_name}{isSelf && " (du)"}
                </span>
                <span className="shrink-0 font-semibold text-[#69A7EA]">{entry.value}</span>
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}

/** Echte statt hartcodierte Warn-Chips (vorher zwei der drei Meldungen als
 * fixer Text, ohne Datenbezug - siehe Nutzer-Feedback "Prozesse
 * abschliessen...", Punkt 1). Beide Zaehl-Meldungen fallen weg, wenn ihr
 * Wert 0 ist, statt eine falsche "0 ..."-Meldung zu zeigen. */
function buildWarnings(cockpit: Cockpit): string[] {
  const overdueCount = cockpit.important.filter(
    (item: CockpitItem) => item.due_at && new Date(item.due_at).getTime() < Date.now(),
  ).length;
  const openInvoiceCount = cockpit.kpis.open_invoice_placement_count;

  const warnings: string[] = [];
  if (overdueCount > 0) {
    warnings.push(
      `${overdueCount} ${overdueCount === 1 ? "Follow-up ist" : "Follow-ups sind"} überfällig und ${overdueCount === 1 ? "braucht" : "brauchen"} eine Entscheidung.`,
    );
  }
  if (openInvoiceCount > 0) {
    warnings.push(
      `${openInvoiceCount} ${openInvoiceCount === 1 ? "Placement hat" : "Placements haben"} offenen Rechnungsstatus.`,
    );
  }
  // Prozesse im Status Offer/Placement ohne erfassten Datensatz - unfertige
  // Erfassungen, die die kaufmaennischen Kennzahlen unterzaehlen (siehe
  // Backend CockpitRead.data_gaps, Nutzer-Entscheidung "KPIs stimmen
  // nicht", Punkt 3d).
  if (cockpit.data_gaps.length > 0) {
    const count = cockpit.data_gaps.length;
    warnings.push(
      `${count} ${count === 1 ? "Prozess hat" : "Prozesse haben"} Status Offer/Placement ohne erfassten Datensatz - Gehalt/Fee nachtragen.`,
    );
  }
  return warnings;
}

// "CV-Outs" zeigt jetzt cv_outs_reached_count (echte CV_OUT-Transition im
// Zeitraum) statt vorher faelschlich cockpit.kpis.submissions (das zaehlt
// im Zeitraum ANGELEGTE Prozesse, unabhaengig vom erreichten Status - siehe
// Backend schemas/operational.py::CockpitKpis-Docstring, Nutzer-Feedback
// "KPIs stimmen nicht", Punkt 3b). "Offers"/"Placements" bleiben bewusst
// die KAUFMAENNISCHEN Zahlen (echte Datensaetze) - dieser Trichter zeigt
// den Fortschritt von der Erfassung her, nicht die reine Pipeline.
// Klick auf Kachel/Balken oeffnet /prozesse vorgefiltert auf die Stufe. Fuer
// Nicht-Admins zusaetzlich "Meine" - das Cockpit zeigt ihnen nur eigene
// Zahlen, die Liste dahinter soll dazu passen.
function processesHref(stage: SubmissionStatus, mineOnly: boolean): string {
  return `/prozesse?stage=${stage}${mineOnly ? "&mine=1" : ""}`;
}

function buildChartData(cockpit: Cockpit, mineOnly: boolean) {
  const rows: [string, number, SubmissionStatus][] = [
    ["Quali Calls", cockpit.kpis.qualification_calls, "qualification_call"],
    ["CV In", cockpit.kpis.cv_available, "cv_in"],
    ["CV-Outs", cockpit.kpis.cv_outs_reached_count, "cv_out"],
    ["Interviews", cockpit.kpis.interviews, "interview"],
    ["Offers", cockpit.kpis.offers, "offer"],
    ["Placements", cockpit.kpis.placements, "placement"],
  ];
  return rows.map(([name, value, stage]) => ({
    name,
    value: Number(value),
    href: processesHref(stage, mineOnly),
  }));
}

export function DashboardCockpit({
  initialCockpit,
  initialSource,
  initialError,
}: {
  initialCockpit: Cockpit;
  initialSource: "api" | "demo" | "error";
  initialError?: string;
}) {
  const cockpit = initialCockpit;
  const source = initialSource;
  const error = initialError;

  const { data: currentUserData } = useCurrentUser();
  const mineOnly = currentUserData ? !currentUserData.data.is_admin : false;
  const chartData = buildChartData(cockpit, mineOnly);
  const warnings = buildWarnings(cockpit);
  // "Offene Fees" fuehrt auf die Placements - Fees/Rechnungsstatus haben in
  // /prozesse keine eigene Filterstufe.
  const quickMetrics: { label: string; value: string | number; Icon: typeof CalendarClock; href: string }[] = [
    { label: "Interviews diese Woche", value: cockpit.kpis.interviews, Icon: CalendarClock, href: processesHref("interview", mineOnly) },
    { label: "Offers offen", value: cockpit.kpis.offers, Icon: FileCheck2, href: processesHref("offer", mineOnly) },
    { label: "Placements", value: cockpit.kpis.placements, Icon: Flame, href: processesHref("placement", mineOnly) },
    { label: "Offene Fees", value: formatCurrency(cockpit.kpis.expected_fees - cockpit.kpis.realized_fees), Icon: ReceiptText, href: processesHref("placement", mineOnly) },
  ];

  return (
    <>
      <PageHeader eyebrow="Operative Schaltzentrale" title="Übersicht" />
      <DemoNotice source={source} error={error} />

      {/* Auf Mobile ein horizontal scrollbarer Streifen aus kompakten Chips
       * (erster hervorgehoben, volle Meldung nur als title-Tooltip) statt
       * drei volle Kaesten uebereinander - ab lg wieder das bekannte Grid mit
       * vollem Fliesstext. */}
      <section className="mb-5 flex gap-2 overflow-x-auto pb-1 lg:grid lg:grid-cols-3 lg:overflow-visible lg:pb-0">
        {warnings.map((warning, index) => (
          <div
            key={warning}
            title={warning}
            className={cn(
              "flex max-w-[240px] shrink-0 items-center gap-2 rounded-full border px-3 py-2 text-[11px] lg:w-full lg:max-w-none lg:shrink lg:rounded-xl lg:text-xs",
              index === 0
                ? "border-[#1F5FA8]/40 bg-[#153A66]/60 text-white"
                : "border-[#D8DADF]/20 bg-[#102A4C]/55 text-[#CBD5E1]",
            )}
          >
            <AlertTriangle size={14} className="shrink-0 text-[#D8DADF]" />
            <span className="overflow-hidden text-ellipsis whitespace-nowrap lg:overflow-visible lg:whitespace-normal">{warning}</span>
          </div>
        ))}
      </section>

      <DashboardTodo items={cockpit.important} />

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <div><div className="flex items-center gap-2"><TimerReset size={17} className="text-[#D8DADF]" /><h2 className="font-semibold">Fällig und überfällig</h2></div><p className="mt-1 text-xs text-[#94A3B8]">Konkrete nächste Schritte mit Prozessbezug</p></div>
            <Badge tone="amber">{cockpit.important.length} offen</Badge>
          </CardHeader>
          <CardContent className="space-y-2">
            {cockpit.important.map((item, index) => <div key={`${item.title}-${index}`} className="flex items-center gap-3 rounded-lg border bg-[#0D1B2E]/75 p-3"><CalendarClock size={15} className="text-[#D8DADF]" /><div className="min-w-0 flex-1"><p className="text-xs font-semibold">{item.title}</p><p className="mt-1 truncate text-xs text-[#94A3B8]">{item.detail}</p></div><span className="text-[10px] text-[#A7ADB7]">{item.due_at ? formatDate(item.due_at) : "Offen"}</span></div>)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div><div className="flex items-center gap-2"><Flame size={17} className="text-[#69A7EA]" /><h2 className="font-semibold">Heiße Prozesse</h2></div><p className="mt-1 text-xs text-[#94A3B8]">Interview, Offer und Placement im Fokus</p></div>
            <Badge tone="blue">{cockpit.hot_processes.length} aktiv</Badge>
          </CardHeader>
          <CardContent className="space-y-2">
            {cockpit.hot_processes.map((item, index) => <div key={`${item.title}-${index}`} className="flex items-center gap-3 rounded-lg border bg-[#0D1B2E]/75 p-3"><span className="size-2 rounded-full bg-[#1F5FA8]" /><div className="min-w-0 flex-1"><p className="text-xs font-semibold">{item.title}</p><p className="mt-1 truncate text-xs text-[#94A3B8]">{item.detail}</p></div><ArrowRight size={14} className="text-[#A7ADB7]" /></div>)}
          </CardContent>
        </Card>
      </section>

      <div className="mb-3 mt-7 flex items-center gap-2"><Gauge size={16} className="text-[#69A7EA]" /><h2 className="text-sm font-semibold">Kurzüberblick</h2></div>
      <section className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {quickMetrics.map(({ label, value, Icon, href }) => <Link key={label} href={href} className="block rounded-xl transition hover:ring-1 hover:ring-[#1F5FA8]/60"><Card><CardContent className="p-4"><Icon size={16} className="text-[#D8DADF]" /><p className="mt-3 text-[11px] text-[#94A3B8]">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p></CardContent></Card></Link>)}
      </section>
      <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader><div><h2 className="font-semibold">KPI-Schnappschuss</h2><p className="mt-1 text-xs text-[#94A3B8]">Detailanalyse liegt in Analytics.</p></div></CardHeader>
          <CardContent><WeeklyChartLoader data={chartData} /></CardContent>
        </Card>
        <LiveRankingCard />
      </section>
    </>
  );
}
