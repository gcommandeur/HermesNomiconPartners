"use client";

// NOMICON: Ansicht "Gesamt" - Rohertrag Direct und Überlassung (gestapelt), Prognose, Alarme,
// Kunden mit beiden Geschäften, Übernahme-Quote. Nur Admins (Server: Ansicht "management").
import Link from "next/link";
import useSWR from "swr";
import { AlertTriangle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorState } from "@/components/crm/error-state";
import { formatMoney } from "@/lib/api/staffing";
import { getManagementOverview, type ManagementPeriod } from "@/lib/api/management";

const PERIOD_LABEL: Record<ManagementPeriod, string> = { week: "7 Tage", month: "30 Tage", quarter: "90 Tage" };

function share(part: string, total: string): number {
  const whole = Number(total);
  return whole > 0 ? Math.max(0, Math.min(100, (Number(part) / whole) * 100)) : 0;
}

export function ManagementOverviewBlock({ period }: { period: ManagementPeriod }) {
  const { data, error, isLoading, mutate } = useSWR(`/management/overview?period=${period}`, () => getManagementOverview(period), { revalidateOnFocus: false });
  if (error) return <ErrorState onRetry={() => void mutate()} />;
  if (isLoading || !data) return <div className="mb-6 h-40 animate-pulse rounded-lg bg-brand-surface" />;
  const m = data.data;
  const gp = m.gross_profit;
  const fc = m.forecast;
  const directShare = share(gp.direct, gp.total);
  const rate = m.takeover.rate === null ? "–" : `${Math.round(Number(m.takeover.rate) * 100)} %`;

  return (
    <section aria-label="Gesamtübersicht" className="mb-8 space-y-4">
      {m.alerts.length > 0 && (
        <div className="flex flex-wrap gap-2" role="list" aria-label="Alarme">
          {m.alerts.map((alert) => (
            <Link
              key={alert.kind}
              role="listitem"
              href={alert.href}
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs ${alert.severity === "red" ? "border-brand-danger/40 bg-brand-danger-soft text-brand-text" : "border-brand-warning/40 bg-brand-warning/10 text-brand-text"}`}
            >
              <AlertTriangle size={13} aria-hidden /> {alert.text}
            </Link>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardContent>
            <h2 className="font-semibold">Rohertrag ({PERIOD_LABEL[period]})</h2>
            <p className="mt-2 text-3xl font-semibold tracking-[-.02em]">{formatMoney(gp.total)}</p>
            <div className="mt-4 flex h-3 overflow-hidden rounded-full bg-brand-surface" role="img" aria-label={`Direct ${formatMoney(gp.direct)}, Überlassung ${formatMoney(gp.staffing)}`}>
              <div className="bg-brand-accent" style={{ width: `${directShare}%` }} />
              <div className="bg-brand-silver" style={{ width: `${Number(gp.total) > 0 ? 100 - directShare : 0}%` }} />
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div><dt className="flex items-center gap-1.5 text-xs text-brand-muted"><span className="size-2 rounded-full bg-brand-accent" aria-hidden />Direct (bezahlte Honorare)</dt><dd className="mt-0.5 font-semibold">{formatMoney(gp.direct)}</dd></div>
              <div><dt className="flex items-center gap-1.5 text-xs text-brand-muted"><span className="size-2 rounded-full bg-brand-silver" aria-hidden />Überlassung (Marge)</dt><dd className="mt-0.5 font-semibold">{formatMoney(gp.staffing)}</dd></div>
            </dl>
            {gp.staffing_missing_rates > 0 && <p className="mt-2 text-xs text-brand-warning">{gp.staffing_missing_rates} freigegebene Stundenzettel ohne Satz oder Lohn sind nicht enthalten.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <h2 className="font-semibold">Prognose</h2>
            <p className="mt-2 text-3xl font-semibold tracking-[-.02em]">{formatMoney(fc.total)}</p>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-xs text-brand-muted">Direct (Fee × Wahrscheinlichkeit)</dt><dd className="mt-0.5 font-semibold">{formatMoney(fc.direct_weighted)}</dd></div>
              <div><dt className="text-xs text-brand-muted">Überlassung (bis Einsatzende)</dt><dd className="mt-0.5 font-semibold">{formatMoney(fc.staffing_margin)}</dd></div>
            </dl>
            {(fc.direct_without_probability > 0 || fc.direct_without_fee > 0 || fc.staffing_excluded > 0) && (
              <p className="mt-2 text-xs text-brand-warning">
                Nicht enthalten, weil Angaben fehlen: {fc.direct_without_fee} Prozesse ohne Fee, {fc.direct_without_probability} ohne Wahrscheinlichkeit, {fc.staffing_excluded} Einsätze ohne Satz, Lohn, Wochenstunden oder Ende.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-semibold">Kunden mit beiden Geschäften</h2>
            <p className="text-xs text-brand-muted">Übernahme-Quote aus Überlassung: <strong>{rate}</strong> ({m.takeover.taken_over} von {m.takeover.pairs} Paaren)</p>
          </div>
          {m.both_business_clients.length === 0 ? (
            <p className="mt-3 text-sm text-brand-muted">Noch kein Kunde mit Vermittlung und Überlassung.</p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead><tr className="border-b border-white/10 text-[9.5px] uppercase tracking-wider text-brand-muted"><th className="py-2 pr-3">Kunde</th><th className="px-3 py-2 text-right">Prozesse</th><th className="px-3 py-2 text-right">Vermittelt</th><th className="px-3 py-2 text-right">Einsätze</th><th className="px-3 py-2 text-right">Übernommen</th></tr></thead>
                <tbody>
                  {m.both_business_clients.map((c) => (
                    <tr key={c.client_id} className="border-b border-white/5">
                      <td className="py-2.5 pr-3 font-medium"><Link href={`/kanzleien/${c.client_id}`} className="hover:underline">{c.client_name}</Link></td>
                      <td className="px-3 py-2.5 text-right">{c.processes}</td>
                      <td className="px-3 py-2.5 text-right">{c.placements}</td>
                      <td className="px-3 py-2.5 text-right">{c.assignments}</td>
                      <td className="px-3 py-2.5 text-right">{c.taken_over}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <details className="rounded-lg border border-white/10 p-3 text-xs text-brand-muted">
        <summary className="cursor-pointer font-medium text-brand-soft">Annahmen der Berechnung (Arbeitgeber-Faktor {m.employer_factor})</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5">{m.assumptions.map((line) => <li key={line}>{line}</li>)}</ul>
      </details>
    </section>
  );
}
