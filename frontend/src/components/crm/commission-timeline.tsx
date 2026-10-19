"use client";

// NOMICON: Meine Provision - Zeitstrahl: drei Kacheln (Monat, Quartal bisher, nächste Rolle),
// Fortschrittsbalken, Diagramm der letzten 12 Monate und Monatstabelle. Abgerechnet wird weiter je
// Quartal; der Monatswert ist der Anteil des Monats an der Quartalsprovision (Stufen laufen mit),
// der laufende Monat ist vorläufig. Nur die Daten einer Person, keine Marge, keine Firmenkosten.
import { Bar, CartesianGrid, Cell, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorState } from "@/components/crm/error-state";
import { eur } from "@/lib/api/commission";
import type { MyCommissionTimeline } from "@/lib/api/my-commission";
import { useMyCommissionTimeline } from "@/lib/api/my-commission-hooks";
import { barWidth, daysToQuarterEndText, monthLabel, nextRoleText, provisionalNote, quarterBoundaryLabels, timelineChartData } from "@/lib/commission-ui";
import { formatPercent } from "@/lib/format";

const REVENUE_COLOR = "#1F5FA8";
const CURRENT_COLOR = "#7FB3EA";
const COMMISSION_COLOR = "#E2B04A";
const AXIS_TICK = { fill: "#94A3B8", fontSize: 11 };

function Tile({ label, value, hint, hint2 }: { label: string; value: string; hint?: string; hint2?: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">{label}</p>
        <p className="mt-1 text-2xl font-semibold tracking-[-.02em]">{value}</p>
        {hint && <p className="mt-0.5 text-xs text-brand-muted">{hint}</p>}
        {hint2 && <p className="text-xs text-brand-muted">{hint2}</p>}
      </CardContent>
    </Card>
  );
}

export function CommissionTimeline({ person }: { person: string | null }) {
  const { data, error, isLoading, mutate } = useMyCommissionTimeline(person);
  const value = data?.data;
  if (error) return <ErrorState onRetry={() => void mutate()} />;
  if (isLoading || !value) return <div className="h-40 animate-pulse rounded-xl bg-brand-surface" aria-busy="true" aria-label="Zeitstrahl wird geladen" />;
  return <TimelineBody data={value} />;
}

function TimelineBody({ data }: { data: MyCommissionTimeline }) {
  const chart = timelineChartData(data.months);
  const boundaries = quarterBoundaryLabels(chart);
  const current = data.current_month;
  const progress = data.progress;
  const hasRank = Boolean(data.rank_label);
  const nextRoleValue = !progress
    ? "–"
    : progress.is_top_rank
      ? progress.next_band_remaining
        ? eur(progress.next_band_remaining)
        : "Höchste Stufe"
      : eur(progress.remaining);
  return (
    <section className="space-y-4" aria-label="Zeitstrahl der Provision">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Tile
          label="Dieser Monat"
          value={hasRank ? eur(current.total) : eur(current.revenue)}
          hint={hasRank ? `Provision ${eur(current.commission)}` : "Umsatz – noch kein Rang zugewiesen"}
          hint2={hasRank ? `Fix ${eur(current.fixed_pay)} · Bonus ${eur(current.bonus)} · vorläufig` : undefined}
        />
        <Tile
          label="Dieses Quartal bisher"
          value={hasRank ? eur(data.quarter_total) : eur(data.quarter_revenue)}
          hint={`Umsatz ${eur(data.quarter_revenue)}`}
          hint2={hasRank ? `Provision ${eur(data.quarter_commission)} · Bonus ${eur(data.quarter_bonus)}` : undefined}
        />
        <Tile
          label={progress?.is_top_rank ? "Bis zur nächsten Provisionsstufe" : "Bis zur nächsten Rolle"}
          value={nextRoleValue}
          hint={progress ? (progress.is_top_rank ? progress.current_rank_label : `${progress.current_rank_label} → ${progress.next_rank_label}`) : undefined}
          hint2={progress ? daysToQuarterEndText(progress.days_to_quarter_end) : undefined}
        />
      </div>

      {progress && (
        <Card>
          <CardContent className="space-y-2 p-4">
            <p className="text-sm font-medium">{nextRoleText(progress)}</p>
            {!progress.is_top_rank && (
              <>
                <div
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(barWidth(progress.percent))}
                  aria-label="Quartalsumsatz bis zur nächsten Rolle"
                  className="h-3 overflow-hidden rounded-full bg-white/10"
                >
                  <div className="h-full rounded-full bg-brand-accent transition-[width]" style={{ width: `${barWidth(progress.percent)}%` }} />
                </div>
                <p className="text-xs text-brand-muted">
                  {formatPercent(progress.percent, { max: 1 })} der Schwelle · {daysToQuarterEndText(progress.days_to_quarter_end)}
                </p>
              </>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-4">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold">Letzte 12 Monate</h2>
            <span className="text-xs text-brand-muted">Umsatz nach Zahldatum · gestrichelt: Quartalsgrenze</span>
          </div>
          <div className="h-[280px] w-full" role="img" aria-label="Umsatz und Provision je Monat">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chart} margin={{ top: 10, right: 6, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="rgba(148,163,184,.12)" vertical={false} />
                <XAxis dataKey="label" tick={AXIS_TICK} axisLine={false} tickLine={false} interval={0} />
                <YAxis yAxisId="revenue" tick={{ ...AXIS_TICK, fontSize: 10 }} axisLine={false} tickLine={false} width={48} tickFormatter={(v: number) => `${Math.round(v / 1000)}k`} />
                <YAxis yAxisId="commission" orientation="right" tick={{ ...AXIS_TICK, fontSize: 10 }} axisLine={false} tickLine={false} width={44} tickFormatter={(v: number) => `${(v / 1000).toLocaleString("de-DE", { maximumFractionDigits: 1 })}k`} />
                <Tooltip
                  cursor={{ fill: "rgba(31,95,168,.08)" }}
                  contentStyle={{ background: "#0D1B2E", border: "1px solid rgba(148,163,184,.18)", borderRadius: 8, color: "#F8FAFC" }}
                  formatter={(v: number, name: string) => [eur(String(v)), name]}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {boundaries.map((label) => (
                  <ReferenceLine key={label} yAxisId="revenue" x={label} stroke="rgba(148,163,184,.45)" strokeDasharray="4 4" />
                ))}
                <Bar yAxisId="revenue" dataKey="revenue" name="Umsatz" radius={[6, 6, 0, 0]}>
                  {chart.map((d) => (
                    <Cell key={d.key} fill={d.isCurrent ? CURRENT_COLOR : REVENUE_COLOR} stroke={d.isCurrent ? "#F8FAFC" : undefined} />
                  ))}
                </Bar>
                {hasRank && <Line yAxisId="commission" type="monotone" dataKey="commission" name="Provision" stroke={COMMISSION_COLOR} strokeWidth={2} dot={{ r: 3 }} />}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-brand-muted">{provisionalNote(hasRank)}</p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="overflow-x-auto p-4">
          <h2 className="mb-2 text-sm font-semibold">Monatstabelle</h2>
          <table className="w-full min-w-[34rem] text-left text-xs">
            <thead>
              <tr className="text-[9.5px] uppercase tracking-wider text-brand-muted">
                <th className="py-1 pr-2">Monat</th>
                <th className="py-1 pr-2 text-right">Umsatz</th>
                <th className="py-1 pr-2 text-right">Provision</th>
                <th className="py-1 pr-2 text-right">Fix</th>
                <th className="py-1 pr-2 text-right">Bonus</th>
                <th className="py-1 text-right">Summe</th>
              </tr>
            </thead>
            <tbody>
              {[...data.months].reverse().map((m) => (
                <tr key={`${m.year}-${m.month}`} className={`border-t border-white/5 ${m.is_current ? "bg-white/5 font-medium" : ""}`}>
                  <td className="py-1.5 pr-2">
                    {monthLabel(m.year, m.month, true)}
                    {m.is_provisional && <span className="ml-2 rounded-full border border-white/15 px-2 py-0.5 text-[9.5px] text-brand-muted">vorläufig</span>}
                  </td>
                  <td className="py-1.5 pr-2 text-right">{eur(m.revenue)}</td>
                  <td className="py-1.5 pr-2 text-right">{hasRank ? eur(m.commission) : "–"}</td>
                  <td className="py-1.5 pr-2 text-right">{hasRank ? eur(m.fixed_pay) : "–"}</td>
                  <td className="py-1.5 pr-2 text-right">{hasRank ? eur(m.bonus) : "–"}</td>
                  <td className="py-1.5 text-right font-semibold">{hasRank ? eur(m.total) : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </section>
  );
}
