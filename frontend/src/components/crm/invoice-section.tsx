"use client";

import { useState } from "react";
import useSWR from "swr";
import { FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorBanner } from "@/components/crm/error-banner";
import { ApprovalPendingNotice, invalidatePendingApprovals } from "@/components/crm/approval-pending-notice";
import { changeInvoiceStatus, createDraftFee, getPlacementFees } from "@/lib/api/queries";
import { formatDate } from "@/lib/utils";
import type { Fee, InvoiceStatus, Placement } from "@/lib/api/types";

const STATUS_LABELS: Record<InvoiceStatus, string> = {
  draft: "Entwurf",
  issued: "Gestellt",
  due: "Fällig",
  paid: "Bezahlt",
  cancelled: "Storniert",
};

// Gleiche Uebergaenge wie Backend services/invoices.py::ALLOWED_INVOICE_TRANSITIONS.
const NEXT_STEPS: Record<InvoiceStatus, { status: InvoiceStatus; label: string }[]> = {
  draft: [{ status: "issued", label: "Rechnung stellen" }],
  issued: [
    { status: "due", label: "Als fällig markieren" },
    { status: "paid", label: "Als bezahlt markieren" },
  ],
  due: [{ status: "paid", label: "Als bezahlt markieren" }],
  paid: [],
  cancelled: [],
};

function money(value: string): string {
  return Number(value).toLocaleString("de-DE", { style: "currency", currency: "EUR" });
}

function FeeRow({ fee, onChanged }: { fee: Fee; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function move(status: InvoiceStatus) {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const result = await changeInvoiceStatus(fee.id, status);
      if (result.approval_request) {
        setInfo("Wartet auf Freigabe durch die Geschäftsführung.");
      }
      await invalidatePendingApprovals("fee", fee.id);
      onChanged();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Status konnte nicht geändert werden.");
    } finally {
      setBusy(false);
    }
  }

  const canCancel = fee.invoice_status !== "paid" && fee.invoice_status !== "cancelled";
  return (
    <div className="rounded-lg border border-white/10 bg-[#0D1B2E]/70 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm">
          <FileText size={14} className="text-[#94A3B8]" />
          <span className="font-medium text-[#F8FAFC]">{money(fee.amount_net)} netto</span>
          <span className="text-xs text-[#94A3B8]">({money(fee.amount_gross)} brutto)</span>
          <Badge tone={fee.invoice_status === "paid" ? "green" : fee.invoice_status === "cancelled" ? "red" : "blue"}>
            {STATUS_LABELS[fee.invoice_status]}
          </Badge>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {NEXT_STEPS[fee.invoice_status].map((step) => (
            <Button key={step.status} type="button" size="sm" disabled={busy} onClick={() => void move(step.status)}>
              {step.label}
            </Button>
          ))}
          {canCancel && (
            <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => void move("cancelled")}>
              Stornieren
            </Button>
          )}
        </div>
      </div>
      <p className="mt-1.5 text-[11px] text-[#747C89]">
        {fee.invoice_date && <>Rechnungsdatum {formatDate(fee.invoice_date)} · </>}
        {fee.paid_at ? <>Bezahlt am {formatDate(fee.paid_at)}</> : <>Angelegt {formatDate(fee.created_at)}</>}
      </p>
      <ApprovalPendingNotice entityType="fee" entityId={fee.id} />
      {info && <p className="mt-2 text-xs text-[#F0B429]">{info}</p>}
      <ErrorBanner message={error} className="mt-2" />
    </div>
  );
}

/** Rechnung zum Placement: als Entwurf anlegen (Betrag = berechnete Fee),
 * dann Entwurf -> Gestellt -> Fällig -> Bezahlt. "Rechnung stellen" durch
 * Nicht-Admins wartet auf Freigabe (siehe /freigaben). */
export function InvoiceSection({ placement }: { placement: Placement }) {
  const key = `/placements/${placement.id}/fees`;
  const { data, mutate } = useSWR(key, () => getPlacementFees(placement.id), { revalidateOnFocus: false });
  const fees = data?.data ?? [];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function createDraft() {
    setBusy(true);
    setError(null);
    try {
      await createDraftFee(placement.id, placement.calculated_fee);
      await mutate();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Rechnung konnte nicht angelegt werden.");
    } finally {
      setBusy(false);
    }
  }

  const hasOpenInvoice = fees.some((fee) => fee.invoice_status !== "cancelled");
  return (
    <div className="mt-5 border-t border-white/10 pt-4">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">Rechnung</p>
      <div className="space-y-2">
        {fees.map((fee) => (
          <FeeRow key={fee.id} fee={fee} onChanged={() => void mutate()} />
        ))}
      </div>
      {!hasOpenInvoice && (
        <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => void createDraft()} className="mt-2">
          Rechnung als Entwurf anlegen ({placement.calculated_fee.toLocaleString("de-DE", { style: "currency", currency: "EUR" })} netto)
        </Button>
      )}
      <ErrorBanner message={error} className="mt-2" />
    </div>
  );
}
