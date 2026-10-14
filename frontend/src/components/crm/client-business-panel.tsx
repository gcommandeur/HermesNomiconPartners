"use client";

// NOMICON: Block "Geschäft mit dieser Kanzlei" auf der Kanzleiseite - Prozesse, Einsätze, Fristen und
// Umsatz. Abschnitte erscheinen nur mit der jeweiligen Ansicht; Beträge nur für Admins.
import Link from "next/link";
import useSWR from "swr";
import { Card, CardContent } from "@/components/ui/card";
import { apiGet } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { ASSIGNMENT_STATUS_LABELS, formatMoney, formatRemaining, type StaffingAssignmentStatus } from "@/lib/api/staffing";
import { stageLabel } from "@/lib/api/engagement";
import { formatDate } from "@/lib/utils";
import { TrafficBadge } from "./staffing-ui";

type ClientBusiness = components["schemas"]["ClientBusinessRead"];

export function ClientBusinessPanel({ clientId }: { clientId: string }) {
  const { data, error } = useSWR(`/clients/${clientId}/business`, () =>
    apiGet<ClientBusiness>(`/clients/${clientId}/business`, { processes: null, assignments: null, deadlines: null, revenue: null }),
  );
  if (error) return null; // der Block ist eine Ergänzung: kein Fehler-Banner auf der Kanzleiseite
  if (!data) return <div className="mt-6 h-24 animate-pulse rounded-lg bg-brand-surface" />;
  const b = data.data;
  if (!b.processes && !b.assignments && !b.revenue) return null;
  return (
    <section className="mt-6" aria-label="Geschäft mit dieser Kanzlei">
      <h2 className="mb-3 font-semibold">Geschäft mit dieser Kanzlei</h2>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {b.processes && (
          <Card>
            <CardContent>
              <h3 className="text-sm font-semibold">Prozesse (Direct)</h3>
              {b.processes.length === 0 ? <p className="mt-2 text-xs text-brand-muted">Keine Prozesse in deinem Bereich.</p> : (
                <ul className="mt-2 space-y-1.5 text-sm">
                  {b.processes.map((p) => (
                    <li key={p.id} className="flex justify-between gap-3">
                      <span className="truncate">{p.candidate_name} <span className="text-brand-muted">· {stageLabel(p.status)}{p.owner_name ? ` (${p.owner_name})` : ""}</span></span>
                      {p.expected_fee && <span className="shrink-0 text-brand-soft">{formatMoney(p.expected_fee)}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        )}
        {b.assignments && (
          <Card>
            <CardContent>
              <h3 className="text-sm font-semibold">Einsätze (Überlassung)</h3>
              {b.assignments.length === 0 ? <p className="mt-2 text-xs text-brand-muted">Keine Einsätze in deinem Bereich.</p> : (
                <ul className="mt-2 space-y-1.5 text-sm">
                  {b.assignments.map((a) => (
                    <li key={a.id}>
                      <Link href={`/ueberlassung/einsaetze/${a.id}`} className="flex justify-between gap-3 hover:underline">
                        <span className="truncate">{a.worker_name} <span className="text-brand-muted">· {ASSIGNMENT_STATUS_LABELS[a.status as StaffingAssignmentStatus] ?? a.status}{a.owner_name ? ` (${a.owner_name})` : ""}</span></span>
                        <span className="shrink-0 text-xs text-brand-muted">{formatDate(a.start_date)} – {a.end_date ? formatDate(a.end_date) : "offen"}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              {b.deadlines && b.deadlines.length > 0 && (
                <div className="mt-3 space-y-1.5 border-t border-white/10 pt-3">
                  {b.deadlines.map((d) => (
                    <div key={d.worker_id} className="flex items-center justify-between gap-2 text-xs">
                      <span className="truncate">{d.worker_name}</span>
                      <TrafficBadge traffic={d.traffic} label={formatRemaining(d.days_remaining)} />
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
      {b.revenue && (
        <Card className="mt-4">
          <CardContent className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
            <p><span className="text-xs text-brand-muted">Bezahlte Vermittlungshonorare</span><br /><strong>{formatMoney(b.revenue.placement_fees_paid)}</strong></p>
            <p><span className="text-xs text-brand-muted">Überlassung berechnet (gestellt oder später)</span><br /><strong>{formatMoney(b.revenue.staffing_invoiced)}</strong></p>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
