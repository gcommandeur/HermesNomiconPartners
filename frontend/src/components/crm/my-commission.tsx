"use client";

// NOMICON: Meine Provision. Karrierebalken (links aktueller Rang, Mitte Fortschritt des Quartalsumsatzes
// zur Beförderungsschwelle, rechts nächster Rang) und darunter die nachvollziehbare Rechnung.
// Jeder sieht nur sich selbst; Teamleiter und Admins können im Auswahlfeld Personen wechseln.
import { useState } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorState } from "@/components/crm/error-state";
import { currentQuarter, eur, shiftQuarter } from "@/lib/api/commission";
import type { MyCommission } from "@/lib/api/my-commission";
import { useMyCommission, useMyCommissionPeople } from "@/lib/api/my-commission-hooks";
import { barWidth } from "@/lib/commission-ui";
import { formatNumber, formatPercent } from "@/lib/format";
import { formatDate } from "@/lib/utils";

const selectClass = "h-9 rounded-md border border-white/10 bg-brand-surface px-2 text-sm text-brand-text outline-none focus:border-brand-accent";

export function CareerBar({ data, className = "" }: { data: MyCommission; className?: string }) {
  if (!data.rank_label) {
    return (
      <div className={`rounded-xl border border-white/10 p-4 text-sm text-brand-muted ${className}`}>
        Dir ist noch kein Rang zugewiesen – die Provision wird nach der Zuweisung berechnet.
      </div>
    );
  }
  const width = barWidth(data.progress_percent);
  return (
    <div className={`rounded-xl border border-white/10 bg-brand-surface p-4 ${className}`} aria-label="Karrierestufe und Fortschritt">
      <div className="flex items-center gap-4">
        <div className="min-w-[7rem] text-sm font-semibold text-brand-text">
          <span className="block text-[10px] font-medium uppercase tracking-wider text-brand-muted">Aktuelle Stufe</span>
          {data.rank_label}
        </div>
        <div className="min-w-0 flex-1">
          {data.is_top_rank ? (
            <p className="text-center text-xs text-brand-muted">Quartalsumsatz {eur(data.revenue)}</p>
          ) : (
            <>
              <div
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(width)}
                aria-label="Quartalsumsatz bis zur Beförderungsschwelle"
                className="h-3 overflow-hidden rounded-full bg-white/10"
              >
                <div className="h-full rounded-full bg-brand-accent transition-[width]" style={{ width: `${width}%` }} />
              </div>
              <p className="mt-1 text-center text-xs text-brand-muted">
                {eur(data.revenue)} von {eur(data.promotion_hurdle)} · {formatPercent(data.progress_percent, { max: 1 })}
              </p>
            </>
          )}
        </div>
        <div className="min-w-[7rem] text-right text-sm font-semibold text-brand-text">
          <span className="block text-[10px] font-medium uppercase tracking-wider text-brand-muted">Nächste Stufe</span>
          {data.is_top_rank ? "Höchste Stufe" : data.next_rank_label}
        </div>
      </div>
      {data.promotion_label && (
        <p className="mt-2 text-center text-xs text-brand-success-text">
          Der Umsatz reicht für „{data.promotion_label}“ – die Beförderung setzt ein Admin.
        </p>
      )}
    </div>
  );
}

/** Kompakte Leiste für die Startseite: lädt die eigene Provision, zeigt nichts bei Fehlern. */
export function MyCommissionBar() {
  const { year, quarter } = currentQuarter();
  const { data } = useMyCommission(year, quarter);
  const value = data?.data;
  if (!value) return null;
  return (
    <Link href="/provision" className="mb-6 block focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent" aria-label="Meine Provision öffnen">
      <CareerBar data={value} />
    </Link>
  );
}

export function MyCommissionView() {
  const initial = currentQuarter();
  const [period, setPeriod] = useState(initial);
  const [person, setPerson] = useState<string | null>(null);
  const { data: people } = useMyCommissionPeople();
  const { data, error, isLoading, mutate } = useMyCommission(period.year, period.quarter, person);
  const value = data?.data;
  const choices = people?.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1" role="group" aria-label="Quartal wählen">
          <Button size="icon" variant="outline" aria-label="Voriges Quartal" onClick={() => setPeriod((p) => shiftQuarter(p.year, p.quarter, -1))}><ChevronLeft size={16} /></Button>
          <span className="min-w-[5.5rem] text-center text-sm font-medium">Q{period.quarter} {period.year}</span>
          <Button size="icon" variant="outline" aria-label="Nächstes Quartal" onClick={() => setPeriod((p) => shiftQuarter(p.year, p.quarter, 1))}><ChevronRight size={16} /></Button>
        </div>
        {choices.length > 1 && (
          <select aria-label="Person wählen" className={selectClass} value={person ?? ""} onChange={(e) => setPerson(e.target.value || null)}>
            {choices.map((choice) => (
              <option key={choice.user_id} value={choice.is_self ? "" : choice.user_id}>{choice.is_self ? `${choice.display_name} (ich)` : choice.display_name}</option>
            ))}
          </select>
        )}
      </div>

      {error ? (
        <ErrorState onRetry={() => void mutate()} />
      ) : isLoading || !value ? (
        <div className="h-32 animate-pulse rounded-xl bg-brand-surface" aria-busy="true" aria-label="Wird geladen" />
      ) : (
        <>
          <CareerBar data={value} />
          <Card>
            <CardContent className="space-y-4 p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-sm font-semibold">Provision {value.display_name} · Q{value.quarter} {value.year}</h2>
                <span className="text-xs text-brand-muted">{formatDate(value.period_start)} – {formatDate(value.period_end)}</span>
              </div>
              <dl className="grid grid-cols-1 gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
                <Line label="Quartalsumsatz (bezahlt)" value={eur(value.revenue)} hint={`Vermittlung ${eur(value.revenue_fees)} · Überlassung ${eur(value.revenue_staffing)}`} />
                <Line label="Provision" value={eur(value.commission)} />
                <Line label="Vermittlungsbonus" value={eur(value.bonus)} hint={`${value.placement_deals + value.staffing_deals} Deal(s): ${value.placement_deals} Vermittlung, ${value.staffing_deals} Überlassung`} />
                <Line label="Fixgehalt im Quartal" value={eur(value.fixed_pay)} />
                <Line label="Brutto im Quartal" value={eur(value.gross)} strong />
              </dl>
              <div>
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-brand-muted">So wird gerechnet</h3>
                <ul className="space-y-1 text-sm">
                  {value.explanation.map((line) => <li key={line}>{line}</li>)}
                </ul>
                <p className="mt-2 text-xs text-brand-muted">Brutto = Fixgehalt im Quartal + Provision + Bonus. Der Bonus ist nicht Teil des provisionspflichtigen Umsatzes.</p>
              </div>
              {value.staffing_assignments.length > 0 && (
                <div>
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-brand-muted">Überlassung im Quartal</h3>
                  <table className="w-full text-left text-xs">
                    <thead><tr className="text-[9.5px] uppercase tracking-wider text-brand-muted"><th className="py-1 pr-2">Einsatz</th><th className="py-1 pr-2 text-right">Bezahlte Monate</th><th className="py-1 text-right">Umsatz im Quartal</th></tr></thead>
                    <tbody>
                      {value.staffing_assignments.map((item) => (
                        <tr key={item.assignment_id} className="border-t border-white/5">
                          <td className="py-1.5 pr-2">{item.worker_name}</td>
                          <td className="py-1.5 pr-2 text-right">{formatNumber(item.paid_months)}</td>
                          <td className="py-1.5 text-right">{eur(item.revenue)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {Number(value.expected_revenue) > 0 && (
                <p role="status" className="rounded-lg border border-white/10 p-3 text-xs text-brand-muted">
                  Erwartet: {eur(value.expected_revenue)} aus gestellten, noch nicht bezahlten Rechnungen. Das ist nur ein Hinweis und zählt erst mit der Zahlung.
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function Line({ label, value, hint, strong }: { label: string; value: string; hint?: string; strong?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-white/5 pb-1.5">
      <dt className="text-brand-muted">{label}{hint && <span className="block text-[10.45px]">{hint}</span>}</dt>
      <dd className={strong ? "font-semibold text-brand-text" : ""}>{value}</dd>
    </div>
  );
}
