"use client";

// NOMICON: Hinweis "Dieser Kandidat ist bereits im Austausch: …" mit Bestätigung beim Anlegen eines
// Prozesses oder Einsatzes. Im Sperrmodus (Admin-Einstellung) kommt stattdessen eine Fehlermeldung.
import { Button } from "@/components/ui/button";

export function EngagementConflictNotice({
  message,
  busy,
  onConfirm,
  onCancel,
}: {
  message: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div role="alertdialog" aria-live="polite" className="space-y-3 rounded-lg border border-brand-warning/40 bg-brand-warning/10 p-3 text-xs text-brand-soft">
      <p>{message}</p>
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={busy}>Abbrechen</Button>
        <Button type="button" size="sm" onClick={onConfirm} disabled={busy}>Trotzdem anlegen</Button>
      </div>
    </div>
  );
}
