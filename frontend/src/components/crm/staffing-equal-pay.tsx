"use client";

// NOMICON: Überlassung - Equal Pay mit Folge: „Equal Pay bestätigt am …“ mit Schaltfläche. Ab dem
// Equal-Pay-Datum (Annahme, kein Rechtsrat) soll der Disponent den Lohn prüfen und angleichen und das
// hier bestätigen. Die Bestätigung darf jeder mit Zugriff auf den Einsatz; die Lohnhöhe sehen und
// ändern weiter nur Admins – hier erscheint nie ein Lohnwert, nur Datum und Status.
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/crm/error-banner";
import { invalidateStaffing } from "@/lib/api/staffing-hooks";
import { confirmStaffingEqualPay, unconfirmStaffingEqualPay, type StaffingDeadline } from "@/lib/api/staffing";
import { formatDate } from "@/lib/utils";

export function EqualPayBox({ assignmentId, deadline, editable = true }: { assignmentId?: string | null; deadline: StaffingDeadline; editable?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!deadline.has_chain || !deadline.equal_pay_from) return null;

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await invalidateStaffing();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Aktion fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  const targetId = assignmentId ?? null;
  const canAct = editable && targetId !== null;
  return (
    <div className="mt-4 rounded-lg border border-white/10 p-3 text-xs" data-testid="equal-pay-box">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">Equal Pay</p>
        {deadline.equal_pay_confirmed_on ? (
          <Badge tone="green">Bestätigt am {formatDate(deadline.equal_pay_confirmed_on)}</Badge>
        ) : deadline.equal_pay_open ? (
          <Badge tone="amber">Equal Pay offen</Badge>
        ) : (
          <Badge tone="gray">ab {formatDate(deadline.equal_pay_from)}</Badge>
        )}
      </div>
      <p className="mt-1 text-brand-muted">
        {deadline.equal_pay_reached ? `Gilt seit ${formatDate(deadline.equal_pay_from)}.` : `Gilt ab ${formatDate(deadline.equal_pay_from)}.`}{" "}
        {deadline.equal_pay_confirmed_on
          ? "Lohn geprüft und angeglichen."
          : deadline.equal_pay_open
            ? "Bitte den Lohn prüfen, angleichen und hier bestätigen."
            : "Den Lohn rechtzeitig prüfen."}
      </p>
      <ErrorBanner message={error} />
      {canAct && deadline.equal_pay_confirmed_on && (
        <div className="mt-2">
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => void run(() => unconfirmStaffingEqualPay(targetId))}>Bestätigung zurücknehmen</Button>
        </div>
      )}
      {canAct && !deadline.equal_pay_confirmed_on && deadline.equal_pay_reached && (
        <div className="mt-2">
          <Button size="sm" disabled={busy} onClick={() => void run(() => confirmStaffingEqualPay(targetId))}>
            {busy ? "Speichern…" : "Equal Pay bestätigen"}
          </Button>
        </div>
      )}
    </div>
  );
}
