import { PageHeader } from "@/components/crm/page-header";
import { DemoNotice } from "@/components/crm/demo-notice";
import { Card, CardContent } from "@/components/ui/card";
import { SourcingMetricForm } from "@/components/crm/sourcing-metric-form";
import { getCockpit } from "@/lib/api/queries";
import { formatCurrency } from "@/lib/utils";

export const dynamic = "force-dynamic";

const NO_DATA = "Keine Daten erfasst";

export default async function AnalyticsPage() {
  const result = await getCockpit("week");
  const { kpis, rates, sourcing, recruiting_kpis: recruitingKpis } = result.data;
  const recruitingKpiCards: [string, string][] = [
    ["Time-to-Fill (Median)", recruitingKpis.time_to_fill_days !== null ? `${recruitingKpis.time_to_fill_days} Tage` : NO_DATA],
    ["Time-to-Interview (Median)", recruitingKpis.time_to_interview_days !== null ? `${recruitingKpis.time_to_interview_days} Tage` : NO_DATA],
    ["Ø Fee pro Placement", recruitingKpis.average_fee_per_placement !== null ? formatCurrency(recruitingKpis.average_fee_per_placement) : NO_DATA],
  ];
  const funnel: [string, number | string][] = [
    ["Pitches / InMails", sourcing.has_data ? sourcing.pitches : NO_DATA],
    ["Antworten", sourcing.has_data ? sourcing.responses : NO_DATA],
    ["Positive Antworten", sourcing.has_data ? sourcing.positive_responses : NO_DATA],
    ["Quali Calls", kpis.qualification_calls], ["CV In", kpis.cv_available],
    ["CV-Outs", kpis.submissions], ["Interviews", kpis.interviews],
    ["Offers", kpis.offers], ["Placements", kpis.placements], ["Bezahlte Fees", rates.placement_to_paid ? kpis.placements : 0],
  ];
  const conversions: [string, number | string][] = [
    ["Pitch → Antwort", sourcing.pitch_to_response_rate ?? NO_DATA],
    ["Antwort → Quali Call", sourcing.response_to_qualification_call_rate ?? NO_DATA],
    ["Quali Call → CV In", kpis.qualification_calls ? Math.round(kpis.cv_available / kpis.qualification_calls * 1000) / 10 : NO_DATA],
    ["CV In → CV-Out", kpis.cv_available ? Math.round(kpis.submissions / kpis.cv_available * 1000) / 10 : NO_DATA],
    ["CV-Out → Interview", rates.submission_to_interview], ["Interview → Offer", rates.interview_to_offer],
    ["Offer → Placement", rates.offer_to_placement], ["Placement → bezahlt", rates.placement_to_paid],
  ];
  return <>
    <PageHeader eyebrow="Recruiting Analytics" title="Funnel und Conversions" action={<SourcingMetricForm />} />
    <DemoNotice source={result.source} error={result.error} />
    {/* Ueber den gesamten historischen Bestand berechnet (nicht auf den
     * Cockpit-Zeitraum begrenzt), siehe Backend CockpitService::
     * _recruiting_kpis - ein Median ueber nur eine Woche/einen Monat haette
     * zu wenige Datenpunkte, um aussagekraeftig zu sein. */}
    <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
      {recruitingKpiCards.map(([label, value]) => (
        <Card key={label}><CardContent className="p-4"><p className="text-[11px] text-[#94A3B8]">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p></CardContent></Card>
      ))}
    </div>
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.2fr_.8fr]">
      <Card><CardContent><h2 className="font-semibold">Recruiting Funnel</h2><div className="mt-5 space-y-2">{funnel.map(([label,value],index) => <div key={String(label)} className="mx-auto flex h-11 items-center justify-between rounded-md border bg-[#102A4C]/55 px-4" style={{width:`${100-index*5}%`}}><span className="text-xs text-[#CBD5E1]">{label}</span><strong className={typeof value === "string" ? "text-xs font-normal text-[#8a9095]" : undefined}>{value}</strong></div>)}</div></CardContent></Card>
      <Card><CardContent><h2 className="font-semibold">Conversion Rates</h2><div className="mt-5 divide-y divide-white/10">{conversions.map(([label,value]) => <div key={String(label)} className="py-3"><div className="flex justify-between text-xs"><span className="text-[#CBD5E1]">{label}</span><strong>{typeof value === "string" ? value : `${value} %`}</strong></div><div className="mt-2 h-1.5 rounded-full bg-[#071426]"><div className="h-full rounded-full bg-gradient-to-r from-[#153A66] to-[#69A7EA]" style={{width:`${typeof value === "string" ? 0 : Math.min(value,100)}%`}} /></div></div>)}</div><div className="mt-5 grid grid-cols-2 gap-3"><div className="rounded-lg border p-3"><p className="text-[10px] text-[#94A3B8]">Erwartet</p><p className="mt-2 font-semibold">{formatCurrency(kpis.expected_fees)}</p></div><div className="rounded-lg border p-3"><p className="text-[10px] text-[#94A3B8]">Realisiert</p><p className="mt-2 font-semibold">{formatCurrency(kpis.realized_fees)}</p></div></div></CardContent></Card>
    </div>
  </>;
}
