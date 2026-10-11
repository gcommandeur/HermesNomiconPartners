"use client";

// NOMICON: Überlassung - Rechnung: Zeilen, Summen, Status (Stellen über die Freigabe-Inbox für Nicht-Admins).
import { useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { ErrorBanner } from "@/components/crm/error-banner";
import { useCurrentUser } from "@/lib/api/hooks";
import { invalidateStaffing, useStaffingInvoice } from "@/lib/api/staffing-hooks";
import {
  INVOICE_STATUS_LABELS,
  changeStaffingInvoiceStatus,
  formatMoney,
  type InvoiceStatus,
  type StaffingInvoice,
} from "@/lib/api/staffing";
import { formatDate } from "@/lib/utils";
import { INVOICE_TONE } from "./staffing-billing-view";
import { Fact, LoadError, LoadingRows, labelClass } from "./staffing-ui";

function isoPlus(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function StaffingInvoiceDetailView({ id }: { id: string }) {
  const { data, error, isLoading, mutate } = useStaffingInvoice(id);
  const { data: me } = useCurrentUser();
  const isAdmin = me?.data.is_admin ?? false;
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [issuing, setIssuing] = useState(false);

  if (error) return <LoadError onRetry={() => void mutate()} />;
  if (isLoading || !data) return <LoadingRows />;
  const invoice = data.data;
  if (!invoice) return <p className="text-sm text-brand-muted">Rechnung nicht gefunden.</p>;

  async function change(status: InvoiceStatus, dates?: { invoice_date?: string; payment_due_date?: string }) {
    setBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      const result = await changeStaffingInvoiceStatus(id, status, dates);
      if (result.approval_request) setNotice("Die Freigabe wurde beantragt. Ein Admin entscheidet unter „Freigaben“.");
      await invalidateStaffing();
      setIssuing(false);
    } catch (exception) {
      setActionError(exception instanceof Error ? exception.message : "Aktion fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge tone={INVOICE_TONE[invoice.invoice_status]}>{INVOICE_STATUS_LABELS[invoice.invoice_status]}</Badge>
            {invoice.approval_pending && <Badge tone="amber">Freigabe ausstehend</Badge>}
          </div>
          <h2 className="text-xl font-semibold tracking-[-.02em]">Überlassungsrechnung {invoice.client_name}</h2>
          <p className="mt-1 text-xs text-brand-muted">{formatDate(invoice.period_start)} – {formatDate(invoice.period_end)}</p>
        </div>
        <Actions invoice={invoice} isAdmin={isAdmin} busy={busy} onChange={change} onIssue={() => setIssuing(true)} />
      </div>

      <ErrorBanner message={actionError} />
      {notice && <p role="status" className="rounded-lg border border-brand-success/30 bg-brand-success-bg/30 p-3 text-xs text-brand-success-text">{notice} {isAdmin && <Link href="/freigaben" className="underline">Zu den Freigaben</Link>}</p>}
      {invoice.approval_pending && !notice && (
        <p role="status" className="rounded-lg border border-brand-warning/30 bg-brand-warning/10 p-3 text-xs text-brand-warning">
          „Rechnung stellen“ wartet auf die Entscheidung eines Admins{isAdmin ? <> – <Link href="/freigaben" className="underline">zu den Freigaben</Link></> : "."}
        </p>
      )}

      <Card>
        <CardContent>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
            <Fact label="Rechnungsdatum">{invoice.invoice_date ? formatDate(invoice.invoice_date) : null}</Fact>
            <Fact label="Zahlungsziel">{invoice.payment_due_date ? formatDate(invoice.payment_due_date) : null}</Fact>
            <Fact label="Bezahlt am">{invoice.paid_at ? formatDate(invoice.paid_at) : null}</Fact>
          </div>
          <table className="mt-6 w-full text-sm">
            <thead>
              <tr className="text-left text-[9.5px] uppercase tracking-wider text-brand-muted">
                <th className="pb-2 font-medium">Position</th>
                <th className="pb-2 text-right font-medium">Stunden</th>
                {isAdmin && <><th className="pb-2 text-right font-medium">Satz</th><th className="pb-2 text-right font-medium">Netto</th></>}
              </tr>
            </thead>
            <tbody>
              {invoice.lines.map((line) => (
                <tr key={line.id} className="border-t border-white/5 align-top">
                  <td className="py-2 pr-3">{line.description}</td>
                  <td className="py-2 text-right">{Number(line.hours).toLocaleString("de-DE", { minimumFractionDigits: 2 })}</td>
                  {isAdmin && <><td className="py-2 text-right">{formatMoney(line.rate)}</td><td className="py-2 text-right">{formatMoney(line.amount_net)}</td></>}
                </tr>
              ))}
            </tbody>
            {isAdmin && (
              <tfoot>
                <tr className="border-t border-white/10"><td className="pt-2" colSpan={3}>Netto</td><td className="pt-2 text-right">{formatMoney(invoice.amount_net)}</td></tr>
                <tr><td colSpan={3}>Umsatzsteuer {Number(invoice.vat_rate).toLocaleString("de-DE")} %</td><td className="text-right">{formatMoney((Number(invoice.amount_gross) - Number(invoice.amount_net)).toFixed(2))}</td></tr>
                <tr className="font-semibold"><td colSpan={3}>Brutto</td><td className="text-right">{formatMoney(invoice.amount_gross)}</td></tr>
              </tfoot>
            )}
          </table>
          {!isAdmin && <p className="mt-4 text-xs text-brand-muted">Beträge sehen nur Admins.</p>}
          {invoice.notes && <p className="mt-4 whitespace-pre-line border-t border-white/10 pt-3 text-sm text-brand-soft">{invoice.notes}</p>}
        </CardContent>
      </Card>

      {issuing && <IssueModal isAdmin={isAdmin} busy={busy} onClose={() => setIssuing(false)} onConfirm={(dates) => void change("issued", dates)} />}
    </div>
  );
}

function Actions({ invoice, isAdmin, busy, onChange, onIssue }: {
  invoice: StaffingInvoice;
  isAdmin: boolean;
  busy: boolean;
  onChange: (status: InvoiceStatus) => Promise<void>;
  onIssue: () => void;
}) {
  const status = invoice.invoice_status;
  return (
    <div className="flex flex-wrap gap-2">
      {status === "draft" && !invoice.approval_pending && (
        <Button size="sm" disabled={busy} onClick={onIssue}>{isAdmin ? "Rechnung stellen" : "Stellen beantragen"}</Button>
      )}
      {status === "draft" && <Button size="sm" variant="ghost" disabled={busy} onClick={() => void onChange("cancelled")}>Entwurf verwerfen</Button>}
      {isAdmin && status === "issued" && <Button size="sm" variant="outline" disabled={busy} onClick={() => void onChange("due")}>Als fällig markieren</Button>}
      {isAdmin && (status === "issued" || status === "due") && <Button size="sm" disabled={busy} onClick={() => void onChange("paid")}>Als bezahlt markieren</Button>}
      {isAdmin && (status === "issued" || status === "due") && <Button size="sm" variant="ghost" disabled={busy} onClick={() => void onChange("cancelled")}>Stornieren</Button>}
    </div>
  );
}

function IssueModal({ isAdmin, busy, onClose, onConfirm }: {
  isAdmin: boolean;
  busy: boolean;
  onClose: () => void;
  onConfirm: (dates: { invoice_date: string; payment_due_date: string }) => void;
}) {
  const [invoiceDate, setInvoiceDate] = useState(isoPlus(0));
  const [due, setDue] = useState(isoPlus(14));
  return (
    <Modal title={isAdmin ? "Rechnung stellen" : "Stellen beantragen"} eyebrow="Überlassung" onClose={onClose}>
      <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); onConfirm({ invoice_date: invoiceDate, payment_due_date: due }); }}>
        {!isAdmin && <p className="text-sm text-brand-soft">Das Stellen einer Rechnung muss ein Admin freigeben. Der Antrag erscheint unter „Freigaben“.</p>}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass} htmlFor="inv-date">Rechnungsdatum</label><Input id="inv-date" type="date" required value={invoiceDate} onChange={(e) => setInvoiceDate(e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="inv-due">Zahlungsziel</label><Input id="inv-due" type="date" required min={invoiceDate} value={due} onChange={(e) => setDue(e.target.value)} /></div>
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Abbrechen</Button>
          <Button type="submit" disabled={busy}>{busy ? "Senden…" : isAdmin ? "Rechnung stellen" : "Beantragen"}</Button>
        </div>
      </form>
    </Modal>
  );
}
