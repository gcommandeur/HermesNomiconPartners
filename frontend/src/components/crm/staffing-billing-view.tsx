"use client";

// NOMICON: Überlassung - Abrechnung: abrechenbare Stundenzettel, Rechnungen, CSV für die Lohnabrechnung.
import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Download } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ErrorBanner } from "@/components/crm/error-banner";
import { useCurrentUser } from "@/lib/api/hooks";
import { invalidateStaffing, useBillableTimesheets, useStaffingInvoices } from "@/lib/api/staffing-hooks";
import {
  INVOICE_STATUS_LABELS,
  createStaffingInvoice,
  downloadHoursCsv,
  formatMoney,
  type InvoiceStatus,
  type StaffingBillableTimesheet,
} from "@/lib/api/staffing";
import { formatDate } from "@/lib/utils";
import { EmptyHint, LoadError, LoadingRows, labelClass } from "./staffing-ui";

export const INVOICE_TONE: Record<InvoiceStatus, "gray" | "blue" | "amber" | "green" | "red"> = {
  draft: "gray",
  issued: "blue",
  due: "amber",
  paid: "green",
  cancelled: "red",
};

function firstOfPreviousMonth(): string {
  const now = new Date();
  const d = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function lastOfPreviousMonth(): string {
  const now = new Date();
  const d = new Date(now.getFullYear(), now.getMonth(), 0);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function StaffingBillingView() {
  const { data: me } = useCurrentUser();
  const isAdmin = me?.data.is_admin ?? false;
  return (
    <div className="space-y-8">
      <BillableSection />
      <InvoiceSection isAdmin={isAdmin} />
      {isAdmin && <ExportSection />}
    </div>
  );
}

// --- Abrechenbare Stundenzettel ----------------------------------------------------------------

function BillableSection() {
  const router = useRouter();
  const { data, error, isLoading, mutate } = useBillableTimesheets();
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const groups = useMemo(() => {
    const byClient = new Map<string, { name: string; items: StaffingBillableTimesheet[] }>();
    for (const item of data?.data ?? []) {
      const group = byClient.get(item.client_company_id) ?? { name: item.client_name, items: [] };
      group.items.push(item);
      byClient.set(item.client_company_id, group);
    }
    return [...byClient.entries()];
  }, [data]);

  function toggle(id: string, clientId: string) {
    setSelected((current) => {
      const sameClient = (data?.data ?? []).filter((t) => current.includes(t.timesheet_id) && t.client_company_id === clientId);
      // Eine Rechnung enthält nur einen Kunden: beim Wechsel des Kunden beginnt die Auswahl neu.
      const base = sameClient.length === current.length ? current : [];
      return base.includes(id) ? base.filter((x) => x !== id) : [...base, id];
    });
  }

  async function createInvoice() {
    setBusy(true);
    setActionError(null);
    try {
      const invoice = await createStaffingInvoice(selected);
      setSelected([]);
      await invalidateStaffing();
      router.push(`/ueberlassung/abrechnung/${invoice.id}`);
    } catch (exception) {
      setActionError(exception instanceof Error ? exception.message : "Rechnungsentwurf konnte nicht erstellt werden.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold">Abrechenbare Stundenzettel</h2>
        <Button size="sm" disabled={busy || selected.length === 0} onClick={() => void createInvoice()}>
          {busy ? "Erstelle…" : `Rechnungsentwurf erstellen${selected.length ? ` (${selected.length})` : ""}`}
        </Button>
      </div>
      <ErrorBanner message={actionError} className="mb-3" />
      {error ? (
        <LoadError onRetry={() => void mutate()} />
      ) : isLoading || !data ? (
        <LoadingRows rows={2} />
      ) : groups.length === 0 ? (
        <EmptyHint>Keine freigegebenen Stundenzettel, die noch abgerechnet werden müssen.</EmptyHint>
      ) : (
        <div className="space-y-4">
          {groups.map(([clientId, group]) => (
            <Card key={clientId}>
              <CardContent>
                <h3 className="text-sm font-semibold">{group.name}</h3>
                <ul className="mt-2 divide-y divide-white/5">
                  {group.items.map((item) => (
                    <li key={item.timesheet_id}>
                      <label className="flex cursor-pointer items-center gap-3 py-2.5 text-sm">
                        <input
                          type="checkbox"
                          checked={selected.includes(item.timesheet_id)}
                          disabled={!item.has_rate}
                          onChange={() => toggle(item.timesheet_id, clientId)}
                          aria-label={`${item.worker_name} ${formatDate(item.period_start)} bis ${formatDate(item.period_end)} auswählen`}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate">{item.worker_name}</span>
                          <span className="block text-xs text-brand-muted">{formatDate(item.period_start)} – {formatDate(item.period_end)}</span>
                        </span>
                        <span className="text-right">{Number(item.total_hours).toLocaleString("de-DE", { minimumFractionDigits: 2 })} Std.</span>
                        {!item.has_rate && <Badge tone="amber" title="Ein Admin muss den Verrechnungssatz am Einsatz eintragen.">kein Satz</Badge>}
                      </label>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}

// --- Rechnungen --------------------------------------------------------------------------------

function InvoiceSection({ isAdmin }: { isAdmin: boolean }) {
  const { data, error, isLoading, mutate } = useStaffingInvoices();
  return (
    <section>
      <h2 className="mb-3 font-semibold">Rechnungen</h2>
      {error ? (
        <LoadError onRetry={() => void mutate()} />
      ) : isLoading || !data ? (
        <LoadingRows rows={2} />
      ) : data.data.length === 0 ? (
        <EmptyHint>Noch keine Rechnung.</EmptyHint>
      ) : (
        <ul className="space-y-2">
          {data.data.map((invoice) => (
            <li key={invoice.id}>
              <Link href={`/ueberlassung/abrechnung/${invoice.id}`} className="flex flex-col gap-2 rounded-lg border border-white/10 p-3 transition-colors hover:bg-brand-hover/40 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{invoice.client_name}</p>
                  <p className="truncate text-xs text-brand-muted">
                    {formatDate(invoice.period_start)} – {formatDate(invoice.period_end)} · {invoice.lines.length} Stundenzettel
                    {isAdmin ? ` · netto ${formatMoney(invoice.amount_net)}` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {invoice.approval_pending && <Badge tone="amber">Freigabe ausstehend</Badge>}
                  <Badge tone={INVOICE_TONE[invoice.invoice_status]}>{INVOICE_STATUS_LABELS[invoice.invoice_status]}</Badge>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// --- Export für die Lohnabrechnung (nur Admins) ----------------------------------------------

function ExportSection() {
  const [start, setStart] = useState(firstOfPreviousMonth());
  const [end, setEnd] = useState(lastOfPreviousMonth());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function download(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await downloadHoursCsv(start, end);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Export fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section>
      <h2 className="mb-3 font-semibold">Export für die Lohnabrechnung</h2>
      <Card>
        <CardContent>
          <p className="mb-4 text-sm text-brand-soft">
            CSV mit den vom Kunden <strong>freigegebenen</strong> Stunden je Leiharbeitnehmer und Kunde samt Stammdaten (inkl. Stundenlohn) –
            für Steuerberater oder Lohnsoftware. Das System rechnet keine Löhne, Steuern oder Sozialabgaben.
          </p>
          <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={download}>
            <div><label className={labelClass} htmlFor="ex-from">Von</label><Input id="ex-from" type="date" required value={start} onChange={(e) => setStart(e.target.value)} /></div>
            <div><label className={labelClass} htmlFor="ex-to">Bis</label><Input id="ex-to" type="date" required min={start} value={end} onChange={(e) => setEnd(e.target.value)} /></div>
            <Button type="submit" disabled={busy}><Download size={15} />{busy ? "Erzeuge…" : "CSV herunterladen"}</Button>
          </form>
          <ErrorBanner message={error} className="mt-3" />
        </CardContent>
      </Card>
    </section>
  );
}
