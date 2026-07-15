import { AlertTriangle, ArrowRight, CalendarClock, FileCheck2, Flame, Gauge, ReceiptText, TimerReset } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/crm/page-header";
import { DemoNotice } from "@/components/crm/demo-notice";
import { WeeklyChartLoader } from "@/components/crm/weekly-chart-loader";
import { getCockpit } from "@/lib/api/queries";
import { formatCurrency, formatDate } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const result = await getCockpit("week");
  const cockpit = result.data;
  const chartData = [
    ["Quali Calls", cockpit.kpis.qualification_calls],
    ["CV In", cockpit.kpis.cv_available],
    ["CV-Outs", cockpit.kpis.submissions],
    ["Interviews", cockpit.kpis.interviews],
    ["Offers", cockpit.kpis.offers],
    ["Placements", cockpit.kpis.placements],
  ].map(([name, value]) => ({ name: String(name), value: Number(value) }));
  const warnings = [
    "2 Follow-ups sind überfällig und brauchen heute eine Entscheidung.",
    "1 Placement hat offenen Rechnungsstatus.",
    "Do-not-touch-Kanzleien werden in Mailing/Geo Mapping ausgeschlossen.",
  ];
  const quickMetrics: { label: string; value: string | number; Icon: typeof CalendarClock }[] = [
    { label: "Interviews diese Woche", value: cockpit.kpis.interviews, Icon: CalendarClock },
    { label: "Offers offen", value: cockpit.kpis.offers, Icon: FileCheck2 },
    { label: "Placements", value: cockpit.kpis.placements, Icon: Flame },
    { label: "Offene Fees", value: formatCurrency(cockpit.kpis.expected_fees - cockpit.kpis.realized_fees), Icon: ReceiptText },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Operative Schaltzentrale"
        title="Übersicht"
        action={<div className="flex rounded-lg border bg-[#0D1B2E] p-1 text-xs"><button className="rounded-md bg-[#153A66] px-3 py-2 text-white">Heute</button><button className="px-3 py-2 text-[#94A3B8]">Diese Woche</button><button className="px-3 py-2 text-[#94A3B8]">Monat</button></div>}
      />
      <DemoNotice source={result.source} error={result.error} />

      <section className="mb-5 grid gap-3 lg:grid-cols-3">
        {warnings.map((warning) => (
          <div key={warning} className="flex items-center gap-3 rounded-xl border border-[#D8DADF]/20 bg-[#102A4C]/55 p-3 text-xs text-[#CBD5E1]">
            <AlertTriangle size={15} className="text-[#D8DADF]" />
            {warning}
          </div>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
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
      <section className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {quickMetrics.map(({ label, value, Icon }) => <Card key={label}><CardContent className="p-4"><Icon size={16} className="text-[#D8DADF]" /><p className="mt-3 text-[11px] text-[#94A3B8]">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p></CardContent></Card>)}
      </section>
      <Card>
        <CardHeader><div><h2 className="font-semibold">KPI-Schnappschuss</h2><p className="mt-1 text-xs text-[#94A3B8]">Detailanalyse liegt in Analytics.</p></div></CardHeader>
        <CardContent><WeeklyChartLoader data={chartData} /></CardContent>
      </Card>
    </>
  );
}
