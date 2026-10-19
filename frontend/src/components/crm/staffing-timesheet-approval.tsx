"use client";

// NOMICON: Freigabeseite für den Kunden (ohne Login): Stundenzettel ansehen, freigeben oder ablehnen.
import { useEffect, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ErrorBanner } from "@/components/crm/error-banner";
import { brand } from "@/lib/brand";
import {
  PublicLinkError,
  approvePublicTimesheet,
  getPublicTimesheet,
  rejectPublicTimesheet,
} from "@/lib/api/staffing-public";
import type { PublicTimesheet } from "@/lib/api/staffing";
import { formatDate, formatDateTime } from "@/lib/utils";
import { formatHours } from "@/lib/format"; // NOMICON

type State =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; sheet: PublicTimesheet }
  | { phase: "done"; sheet: PublicTimesheet };

function weekday(iso: string): string {
  return new Intl.DateTimeFormat("de-DE", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date(`${iso}T12:00:00`));
}

export function StaffingTimesheetApproval({ token }: { token: string }) {
  const [state, setState] = useState<State>({ phase: "loading" });
  const [name, setName] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getPublicTimesheet(token)
      .then((sheet) => { if (active) setState({ phase: "ready", sheet }); })
      .catch((exception: unknown) => {
        if (active) setState({ phase: "error", message: exception instanceof Error ? exception.message : "Der Link konnte nicht geladen werden." });
      });
    return () => { active = false; };
  }, [token]);

  async function decide(approve: boolean) {
    setBusy(true);
    setError(null);
    try {
      const sheet = approve ? await approvePublicTimesheet(token, name.trim()) : await rejectPublicTimesheet(token, name.trim(), reason.trim());
      setState({ phase: "done", sheet });
    } catch (exception) {
      // Link ungültig/abgelaufen/gesperrt: endgültige Meldung; Eingabe- und Netzfehler: erneut versuchen.
      if (exception instanceof PublicLinkError && ["invalid", "expired", "rate_limited"].includes(exception.kind)) {
        setState({ phase: "error", message: exception.message });
      } else {
        setError(exception instanceof Error ? exception.message : "Das hat nicht geklappt. Bitte erneut versuchen.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-5 px-4 py-8 sm:py-12">
      <header>
        <p className="text-[9.5px] font-semibold uppercase tracking-[.22em] text-brand-silver">{brand.companyName}</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-[-.025em] text-brand-text">Stundenzettel zur Freigabe</h1>
      </header>

      {state.phase === "loading" && <div className="h-40 animate-pulse rounded-xl bg-brand-surface" aria-busy="true" aria-label="Wird geladen" />}

      {state.phase === "error" && (
        <Card><CardContent className="flex items-start gap-3"><XCircle size={20} className="mt-0.5 text-brand-danger" aria-hidden /><p role="alert" className="text-sm">{state.message}</p></CardContent></Card>
      )}

      {state.phase === "done" && (
        <Card>
          <CardContent className="flex items-start gap-3">
            {state.sheet.status === "approved" ? <CheckCircle2 size={20} className="mt-0.5 text-brand-success" aria-hidden /> : <XCircle size={20} className="mt-0.5 text-brand-warning" aria-hidden />}
            <div role="status">
              <p className="font-semibold">{state.sheet.status === "approved" ? "Vielen Dank – der Stundenzettel ist freigegeben." : "Der Stundenzettel wurde abgelehnt."}</p>
              <p className="mt-1 text-sm text-brand-soft">
                {state.sheet.decided_by_name}, {formatDateTime(state.sheet.decided_at)}.
                {state.sheet.status === "rejected" ? " Wir melden uns mit einer korrigierten Fassung." : ""} Diese Seite kann geschlossen werden.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {state.phase === "ready" && (
        <>
          <Card>
            <CardContent>
              <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div><dt className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">Mitarbeiter/in</dt><dd className="mt-1 text-sm">{state.sheet.worker_name}</dd></div>
                <div><dt className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">Kunde</dt><dd className="mt-1 text-sm">{state.sheet.client_name}</dd></div>
                <div><dt className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">Zeitraum</dt><dd className="mt-1 text-sm">{formatDate(state.sheet.period_start)} – {formatDate(state.sheet.period_end)}</dd></div>
              </dl>
              <table className="mt-5 w-full text-sm">
                <thead>
                  <tr className="text-left text-[9.5px] uppercase tracking-wider text-brand-muted">
                    <th className="pb-2 font-medium">Tag</th><th className="pb-2 text-right font-medium">Stunden</th><th className="pb-2 text-right font-medium">Pause</th>
                  </tr>
                </thead>
                <tbody>
                  {state.sheet.entries.map((entry) => (
                    <tr key={entry.work_date} className="border-t border-white/5">
                      <td className="py-1.5">{weekday(entry.work_date)}</td>
                      <td className="py-1.5 text-right">{formatHours(entry.hours, { fixed: true, unit: "" })}</td>
                      <td className="py-1.5 text-right">{entry.break_minutes} Min.</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-white/10 font-semibold">
                    <td className="pt-2">Summe</td>
                    <td className="pt-2 text-right">{formatHours(state.sheet.total_hours, { fixed: true })}</td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); if (!rejecting) void decide(true); }}>
                <div>
                  <label className="mb-1 block text-xs text-brand-muted" htmlFor="approver">Ihr Name *</label>
                  <Input id="approver" required minLength={2} maxLength={160} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                {rejecting && (
                  <div>
                    <label className="mb-1 block text-xs text-brand-muted" htmlFor="reason">Was stimmt nicht? *</label>
                    <textarea id="reason" required minLength={3} maxLength={2000} rows={3} value={reason} onChange={(e) => setReason(e.target.value)}
                      className="w-full rounded-md border border-white/10 bg-brand-surface px-3 py-2 text-sm text-brand-text outline-none focus:border-brand-accent" />
                  </div>
                )}
                <ErrorBanner message={error} />
                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                  {rejecting ? (
                    <>
                      <Button type="button" variant="outline" onClick={() => setRejecting(false)}>Zurück</Button>
                      <Button type="button" disabled={busy || name.trim().length < 2 || reason.trim().length < 3} onClick={() => void decide(false)}>Ablehnen</Button>
                    </>
                  ) : (
                    <>
                      <Button type="button" variant="outline" disabled={busy} onClick={() => setRejecting(true)}>Ablehnen…</Button>
                      <Button type="submit" disabled={busy || name.trim().length < 2}>{busy ? "Wird gesendet…" : "Stunden freigeben"}</Button>
                    </>
                  )}
                </div>
                <p className="text-xs text-brand-muted">
                  Mit der Freigabe bestätigen Sie die oben genannten Stunden. Der Link kann nur einmal verwendet werden{state.sheet.expires_at ? ` und gilt bis ${formatDate(state.sheet.expires_at)}` : ""}.
                </p>
              </form>
            </CardContent>
          </Card>
        </>
      )}
    </main>
  );
}
