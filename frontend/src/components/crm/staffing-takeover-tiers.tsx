"use client";

// NOMICON: Staffel der Übernahme-Fee nach Einsatzdauer (einstellbar, nur Admins). Die Startwerte sind
// Platzhalter und müssen mit der vertraglich vereinbarten Staffel abgeglichen werden.
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ErrorBanner } from "@/components/crm/error-banner";
import { useTakeoverFeeTiers } from "@/lib/api/staffing-hooks";
import { saveTakeoverFeeTiers } from "@/lib/api/staffing";
import { LoadError, LoadingRows } from "./staffing-ui";

type Row = { up_to_months: string; percent_of_fee: string };

export function StaffingTakeoverTiers({ isAdmin }: { isAdmin: boolean }) {
  const { data, error, isLoading, mutate } = useTakeoverFeeTiers();
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    if (data) setRows(data.data.tiers.map((t) => ({ up_to_months: t.up_to_months === null ? "" : String(t.up_to_months), percent_of_fee: String(Number(t.percent_of_fee)) })));
  }, [data]);

  if (error) return <LoadError onRetry={() => void mutate()} />;
  if (isLoading || !data) return <LoadingRows rows={2} />;

  function update(index: number, key: keyof Row, value: string) {
    setMessage(null);
    setRows((current) => current.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    setMessage(null);
    try {
      await saveTakeoverFeeTiers(
        rows.map((row, index) => ({
          up_to_months: index === rows.length - 1 ? null : Number(row.up_to_months),
          percent_of_fee: row.percent_of_fee.replace(",", "."),
        })),
      );
      await mutate();
      setMessage("Gespeichert.");
    } catch (exception) {
      setFailure(exception instanceof Error ? exception.message : "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="font-semibold">Übernahme-Fee nach Einsatzdauer</h2>
        <Badge tone="amber">Platzhalter</Badge>
      </div>
      <Card>
        <CardContent>
          <p className="mb-4 text-xs text-brand-muted">
            Anteil des Vermittlungshonorars (in Prozent des Honorarsatzes des Kunden), wenn der Kunde einen Leiharbeitnehmer nach der genannten Einsatzdauer übernimmt. {data.data.notice}
          </p>
          <form className="space-y-2" onSubmit={save}>
            {rows.map((row, index) => {
              const last = index === rows.length - 1;
              return (
                <div key={index} className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[1fr_1fr]">
                  <label className="flex items-center gap-2 text-sm text-brand-soft">
                    {last ? "Darüber hinaus" : "Bis einschließlich"}
                    {!last && <Input aria-label={`Monate Stufe ${index + 1}`} type="number" min={1} required disabled={!isAdmin} value={row.up_to_months} onChange={(e) => update(index, "up_to_months", e.target.value)} className="w-24" />}
                    {!last && "Monaten"}
                  </label>
                  <label className="flex items-center gap-2 text-sm text-brand-soft">
                    Anteil
                    <Input aria-label={`Anteil Stufe ${index + 1}`} inputMode="decimal" required disabled={!isAdmin} value={row.percent_of_fee} onChange={(e) => update(index, "percent_of_fee", e.target.value)} className="w-24" /> %
                  </label>
                </div>
              );
            })}
            <ErrorBanner message={failure} />
            {isAdmin ? (
              <div className="mt-3 flex items-center justify-end gap-3">
                {message && <span role="status" className="text-xs text-brand-success-text">{message}</span>}
                <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Speichern"}</Button>
              </div>
            ) : (
              <p className="text-xs text-brand-muted">Nur Admins können die Staffel ändern.</p>
            )}
          </form>
        </CardContent>
      </Card>
    </section>
  );
}
