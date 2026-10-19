"use client";

import { useState } from "react";
import { MailPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { apiPatch, apiPost } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import { invalidateMailingGroupsCache, useMailingGroupsCache } from "@/lib/api/hooks";
import type { MailingGroup, MailingRecipient } from "@/lib/api/types";

/** Konsistente kleine UI-Komponente, ueberall dort einsetzbar, wo eine
 * E-Mail-Adresse angezeigt wird (Kandidaten-/Kunden-/Kontaktprofil, Geo-
 * Mapping-Auswahl) - schreibt immer auf dasselbe Backend-Modell (MailingGroup,
 * siehe Punkt 6/7). Empfaenger koennen zu einer bestehenden Gruppe
 * hinzugefuegt oder als neue Gruppe angelegt werden. */
export function AddToMailingButton({ recipient }: { recipient: MailingRecipient }) {
  const [open, setOpen] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const { data } = useMailingGroupsCache();
  const groups = data?.data ?? [];

  function dedupeKey(item: MailingRecipient): string {
    return item.email ? `email:${item.email.toLowerCase()}` : `${item.kind}:${item.id}`;
  }

  async function addToExisting(group: MailingGroup) {
    setBusy(true);
    setError(null);
    try {
      const merged = new Map(group.recipients.map((item) => [dedupeKey(item), item]));
      merged.set(dedupeKey(recipient), recipient);
      await apiPatch<MailingGroup>(`/mailing-groups/${group.id}`, {
        recipients: Array.from(merged.values()),
      });
      void invalidateMailingGroupsCache();
      setDone(`Zu "${group.name}" hinzugefügt.`);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  async function createNew() {
    if (!newGroupName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await apiPost<MailingGroup>("/mailing-groups", {
        name: newGroupName.trim(),
        recipients: [recipient],
      });
      void invalidateMailingGroupsCache();
      setDone(`Neue Gruppe "${newGroupName.trim()}" angelegt.`);
      setNewGroupName("");
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => { setOpen(true); setDone(null); setError(null); }}>
        <MailPlus size={13} />Für Mailing nutzen
      </Button>
      {open && (
        <Modal title="Für Mailing nutzen" eyebrow={recipient.name} onClose={() => setOpen(false)}>
          <div className="space-y-4">
            {done && (
              <div className="rounded-lg border border-brand-success/35 bg-brand-success-bg/45 p-3 text-xs text-brand-success-text">{done}</div>
            )}
            <ErrorBanner message={error} />
            {groups.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand-gray">
                  Zu bestehender Gruppe hinzufügen
                </p>
                <div className="max-h-52 space-y-1.5 overflow-y-auto">
                  {groups.map((group) => (
                    <button
                      key={group.id}
                      type="button"
                      disabled={busy}
                      onClick={() => addToExisting(group)}
                      className="flex w-full items-center justify-between rounded-md border border-white/10 bg-brand-surface px-3 py-2 text-left text-xs hover:border-brand-accent/50 disabled:opacity-50"
                    >
                      <span>{group.name}</span>
                      <span className="text-brand-gray">{group.recipients.length} Empfänger</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="border-t border-white/10 pt-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-brand-gray">Neue Gruppe anlegen</p>
              <div className="flex gap-2">
                <Input placeholder="Name der Gruppe" value={newGroupName} onChange={(e) => setNewGroupName(e.target.value)} />
                <Button size="sm" disabled={busy || !newGroupName.trim()} onClick={createNew}>Anlegen</Button>
              </div>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
