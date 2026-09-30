"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { Check, ShieldOff, X } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorState } from "@/components/crm/error-state";
import { ErrorBanner } from "@/components/crm/error-banner";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/lib/api/hooks";
import { approveApprovalRequest, getApprovalRequests, rejectApprovalRequest } from "@/lib/api/queries";
import { formatDate } from "@/lib/utils";
import type { ApprovalKind, ApprovalRequest } from "@/lib/api/types";

const KIND_LABELS: Record<ApprovalKind, string> = {
  new_client: "Neue Kanzlei",
  honorar_change: "Honorar-Änderung",
  invoice_issue: "Rechnung stellen",
};

const FIELD_LABELS: Record<string, string> = {
  name: "Name",
  city: "Ort",
  postal_code: "PLZ",
  fee_percentage: "Honorar %",
  honorar_stufe: "Honorarstufe",
  nachlass_begruendung: "Nachlass-Begründung",
  guarantee_period_months: "Garantie (Monate)",
  payment_terms_days: "Zahlungsziel (Tage)",
  refund_terms: "Rückerstattung",
  special_terms: "Sonderkonditionen",
  amount_net: "Betrag netto (€)",
  amount_gross: "Betrag brutto (€)",
  invoice_status: "Rechnungsstatus",
};

// Interne Felder, die in der Inbox nichts zu suchen haben.
const HIDDEN_FIELDS = new Set(["label"]);

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function ValuesTable({ request }: { request: ApprovalRequest }) {
  const proposed = request.proposed_values ?? {};
  const old = request.old_values ?? {};
  const keys = Object.keys(proposed).filter((key) => !HIDDEN_FIELDS.has(key));
  const showOld = request.kind !== "new_client";
  if (keys.length === 0) return null;
  return (
    <table className="mt-3 w-full text-xs">
      <thead>
        <tr className="text-left text-[10px] uppercase tracking-wider text-[#94A3B8]">
          <th className="pb-1 pr-3 font-medium">Feld</th>
          {showOld && <th className="pb-1 pr-3 font-medium">Bisher</th>}
          <th className="pb-1 font-medium">{showOld ? "Neu" : "Wert"}</th>
        </tr>
      </thead>
      <tbody>
        {keys.map((key) => (
          <tr key={key} className="border-t border-white/5">
            <td className="py-1.5 pr-3 text-[#94A3B8]">{FIELD_LABELS[key] ?? key}</td>
            {showOld && <td className="py-1.5 pr-3 text-[#CBD5E1]">{display(old[key])}</td>}
            <td className="py-1.5 font-medium text-[#F8FAFC]">{display(proposed[key])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function FreigabenPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const { data, error, isLoading, mutate } = useSWR(isAdmin ? "/approval-requests" : null, getApprovalRequests, {
    revalidateOnFocus: true,
  });
  const requests = data?.data ?? [];
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectNote, setRejectNote] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  async function decide(id: string, action: "approve" | "reject") {
    setBusyId(id);
    setActionError(null);
    try {
      if (action === "approve") await approveApprovalRequest(id);
      else await rejectApprovalRequest(id, rejectNote.trim() || null);
      setRejectingId(null);
      setRejectNote("");
      await mutate();
    } catch (exception) {
      setActionError(exception instanceof Error ? exception.message : "Entscheidung fehlgeschlagen.");
    } finally {
      setBusyId(null);
    }
  }

  if (meLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="h-20 animate-pulse rounded-lg bg-[#0D1B2E]" />
        ))}
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow="Hermes" title="Freigaben" />
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ShieldOff size={28} className="text-[#94A3B8]" />
            <p className="text-sm font-semibold text-[#F8FAFC]">Nur für Admins zugänglich</p>
            <p className="max-w-sm text-xs text-[#94A3B8]">
              Hier entscheidet die Geschäftsführung über neue Kanzleien, Honorar-Änderungen und
              das Stellen von Rechnungen.
            </p>
          </CardContent>
        </Card>
      </>
    );
  }

  if (error) return <ErrorState onRetry={() => void mutate()} />;

  return (
    <>
      <PageHeader eyebrow="Hermes" title="Freigaben" />
      <ErrorBanner message={actionError} className="mb-3" />
      {isLoading && <div className="h-24 animate-pulse rounded-lg bg-[#0D1B2E]" />}
      {!isLoading && requests.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-[#94A3B8]">
            Keine offenen Freigaben.
          </CardContent>
        </Card>
      )}
      <div className="space-y-3">
        {requests.map((request) => (
          <Card key={request.id}>
            <CardContent className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="amber">{KIND_LABELS[request.kind] ?? request.kind}</Badge>
                    {request.entity_type === "client_company" ? (
                      <Link href={`/kanzleien/${request.entity_id}`} className="text-sm font-semibold text-[#F8FAFC] hover:underline">
                        {request.entity_label ?? "Kanzlei"}
                      </Link>
                    ) : (
                      <span className="text-sm font-semibold text-[#F8FAFC]">{request.entity_label ?? "Rechnung"}</span>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-[#94A3B8]">
                    Angefragt von {request.requested_by ?? "unbekannt"} · {formatDate(request.requested_at)}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button size="sm" disabled={busyId === request.id} onClick={() => void decide(request.id, "approve")}>
                    <Check size={14} />Genehmigen
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busyId === request.id}
                    onClick={() => {
                      setRejectingId(rejectingId === request.id ? null : request.id);
                      setRejectNote("");
                    }}
                  >
                    <X size={14} />Ablehnen
                  </Button>
                </div>
              </div>
              <ValuesTable request={request} />
              {rejectingId === request.id && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <input
                    value={rejectNote}
                    onChange={(event) => setRejectNote(event.target.value)}
                    placeholder="Begründung (optional)"
                    className="h-9 min-w-0 flex-1 rounded-md border border-white/15 bg-white/5 px-3 text-xs text-[#D8DADF] placeholder:text-[#5b6167] focus:outline-none focus:ring-2 focus:ring-[#1F5FA8]/30"
                  />
                  <Button size="sm" variant="outline" disabled={busyId === request.id} onClick={() => void decide(request.id, "reject")}>
                    Ablehnung bestätigen
                  </Button>
                </div>
              )}
              {request.kind === "new_client" && rejectingId === request.id && (
                <p className="mt-2 text-[11px] text-[#94A3B8]">
                  Eine abgelehnte neue Kanzlei wird nicht gelöscht, sondern als „Gesperrt“ markiert.
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}
