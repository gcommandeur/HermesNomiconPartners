"use client";

import { useMemo, useState } from "react";
import { Check, Combine, Copy, Mail, Pencil, Trash2, Users, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { apiDelete, apiPatch, apiPost } from "@/lib/api/client";
import { sendBulkMail } from "@/lib/api/queries";
import { ErrorBanner } from "@/components/crm/error-banner";
import {
  invalidateMailingGroupsCache,
  useEmailTemplatesCache,
  useMailingGroupsCache,
} from "@/lib/api/hooks";
import type { MailingGroup } from "@/lib/api/types";

function renderTemplate(text: string, values: Record<string, string>): string {
  return text.replace(/\{(\w+)\}/g, (match, key: string) => values[key] ?? match);
}

const selectClass = "h-9 rounded-md border border-white/10 bg-brand-sidebar px-2 text-xs text-brand-text outline-none focus:border-brand-accent";

export function MailingGroupsPanel({
  initialPreviewGroupId = null,
}: {
  /** Oeffnet die Vorschau/Versand-Vorlage direkt fuer diese Gruppe (z.B.
   * "?group=<id>" von der CV-Out-Kampagne am Kandidaten aus, siehe
   * cv-out-campaign-modal.tsx) - erspart den zusaetzlichen Klick auf
   * "Vorschau" nach dem Anlegen der Gruppe. */
  initialPreviewGroupId?: string | null;
}) {
  const { data, isLoading } = useMailingGroupsCache();
  const groups = useMemo(() => data?.data ?? [], [data]);
  // Live aus dem selben SWR-Key wie EmailTemplatesPanel - eine dort
  // gespeicherte Bearbeitung ist hier ohne Reload sofort sichtbar (Auftrag
  // "Mailvorlagen editierbar machen").
  const { data: templatesResult, isLoading: templatesLoading } = useEmailTemplatesCache();
  const templates = useMemo(() => templatesResult?.data ?? [], [templatesResult]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [previewGroupId, setPreviewGroupId] = useState<string | null>(initialPreviewGroupId);
  const [previewTemplateKey, setPreviewTemplateKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeName, setMergeName] = useState("");
  const [overwriteId, setOverwriteId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameBusy, setRenameBusy] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  function toggleSelect(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function assignTemplate(group: MailingGroup, templateKey: string) {
    setError(null);
    try {
      await apiPatch<MailingGroup>(`/mailing-groups/${group.id}`, {
        template_key: templateKey || null,
      });
      void invalidateMailingGroupsCache();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Vorlage konnte nicht zugeordnet werden.");
    }
  }

  function startRename(group: MailingGroup) {
    setError(null);
    setRenamingId(group.id);
    setRenameValue(group.name);
  }

  function cancelRename() {
    setRenamingId(null);
    setRenameValue("");
  }

  async function saveRename(group: MailingGroup) {
    const trimmed = renameValue.trim();
    if (!trimmed || trimmed === group.name) {
      cancelRename();
      return;
    }
    setRenameBusy(true);
    setError(null);
    try {
      await apiPatch<MailingGroup>(`/mailing-groups/${group.id}`, { name: trimmed });
      void invalidateMailingGroupsCache();
      cancelRename();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Gruppe konnte nicht umbenannt werden.");
    } finally {
      setRenameBusy(false);
    }
  }

  async function handleDelete(group: MailingGroup) {
    if (!window.confirm(`Gruppe "${group.name}" wirklich löschen?`)) return;
    setDeletingId(group.id);
    setError(null);
    try {
      await apiDelete(`/mailing-groups/${group.id}`);
      void invalidateMailingGroupsCache();
      setSelectedIds((current) => {
        if (!current.has(group.id)) return current;
        const next = new Set(current);
        next.delete(group.id);
        return next;
      });
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Gruppe konnte nicht gelöscht werden.");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleMerge() {
    if (!mergeName.trim() || selectedIds.size < 2) return;
    setBusy(true);
    setError(null);
    try {
      await apiPost<MailingGroup>("/mailing-groups/merge", {
        group_ids: Array.from(selectedIds),
        target_name: mergeName.trim(),
        overwrite_group_id: overwriteId || null,
      });
      void invalidateMailingGroupsCache();
      setMessage(`${selectedIds.size} Gruppen zu "${mergeName.trim()}" zusammengeführt.`);
      setMergeOpen(false);
      setMergeName("");
      setOverwriteId("");
      setSelectedIds(new Set());
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Zusammenführen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  const previewGroup = groups.find((group) => group.id === previewGroupId) ?? null;
  const activeTemplateKey = previewTemplateKey ?? previewGroup?.template_key ?? null;
  const selectedTemplate = templates.find((template) => template.key === activeTemplateKey) ?? null;
  const exampleRecipient = previewGroup?.recipients[0];
  const renderedSubject = selectedTemplate && exampleRecipient
    ? renderTemplate(selectedTemplate.subject, { contact: exampleRecipient.name, candidate: exampleRecipient.name, client: exampleRecipient.name })
    : selectedTemplate?.subject ?? "";
  const renderedBody = selectedTemplate && exampleRecipient
    ? renderTemplate(selectedTemplate.body, { contact: exampleRecipient.name, candidate: exampleRecipient.name, client: exampleRecipient.name })
    : selectedTemplate?.body ?? "";

  async function handleCopy() {
    if (!selectedTemplate) return;
    await navigator.clipboard.writeText(`Betreff: ${renderedSubject}\n\n${renderedBody}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const [bulkSending, setBulkSending] = useState(false);
  const [bulkSendMessage, setBulkSendMessage] = useState<string | null>(null);

  async function handleBulkSend() {
    if (!previewGroup || !selectedTemplate) return;
    if (
      !window.confirm(
        `Diese Mail jetzt an alle ${previewGroup.recipients.length} Empfänger:innen von "${previewGroup.name}" senden? Alle erhalten denselben Text (keine Personalisierung pro Empfänger:in).`,
      )
    ) {
      return;
    }
    setBulkSending(true);
    setError(null);
    setBulkSendMessage(null);
    try {
      const result = await sendBulkMail({
        mailing_group_id: previewGroup.id,
        subject: renderedSubject,
        body_text: renderedBody,
      });
      setBulkSendMessage(
        `${result.sent_count} Mail(s) versendet.` +
          (result.failed.length > 0
            ? ` ${result.failed.length} fehlgeschlagen: ${result.failed.join("; ")}`
            : "") +
          (result.skipped_due_to_daily_limit_count > 0
            ? ` ${result.skipped_due_to_daily_limit_count} wegen Tageslimit übersprungen.`
            : ""),
      );
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Versand fehlgeschlagen.");
    } finally {
      setBulkSending(false);
    }
  }

  if (isLoading || templatesLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="h-16 animate-pulse rounded-lg bg-brand-surface" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {message && <div className="rounded-lg border border-brand-success/35 bg-brand-success-bg/45 p-3 text-xs text-brand-success-text">{message}</div>}
      <ErrorBanner message={error} />

      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-semibold"><Users size={16} />Gespeicherte Mailing-Gruppen</h2>
        <Button
          size="sm"
          variant="outline"
          disabled={selectedIds.size < 2}
          onClick={() => setMergeOpen(true)}
        >
          <Combine size={14} />Gruppen zusammenführen ({selectedIds.size})
        </Button>
      </div>

      {groups.length === 0 && (
        <Card><CardContent className="py-12 text-center text-sm text-brand-gray">
          Noch keine Mailing-Gruppen gespeichert — auf Kandidaten-/Kunden-/Kontaktprofilen oder im Geo Mapping über &quot;Für Mailing nutzen&quot; anlegen.
        </CardContent></Card>
      )}

      <div className="space-y-2">
        {groups.map((group) => (
          <Card key={group.id}>
            <CardContent className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={selectedIds.has(group.id)}
                  onChange={() => toggleSelect(group.id)}
                  aria-label={`${group.name} auswählen`}
                />
                <div className="min-w-0">
                  {renamingId === group.id ? (
                    <div className="flex items-center gap-1">
                      <Input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") void saveRename(group);
                          if (e.key === "Escape") cancelRename();
                        }}
                        className="h-8 w-48"
                      />
                      <Button size="icon" variant="ghost" disabled={renameBusy} onClick={() => saveRename(group)} aria-label="Umbenennen speichern">
                        <Check size={14} />
                      </Button>
                      <Button size="icon" variant="ghost" disabled={renameBusy} onClick={cancelRename} aria-label="Umbenennen abbrechen">
                        <X size={14} />
                      </Button>
                    </div>
                  ) : (
                    <p className="font-semibold">{group.name}</p>
                  )}
                  <p className="mt-1 text-xs text-brand-muted">{group.recipients.length} Empfänger:innen</p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  className={selectClass}
                  value={group.template_key ?? ""}
                  onChange={(e) => assignTemplate(group, e.target.value)}
                >
                  <option value="">Keine Vorlage zugeordnet</option>
                  {templates.map((template) => (
                    <option key={template.key} value={template.key}>{template.name}</option>
                  ))}
                </select>
                <Button size="sm" variant="outline" onClick={() => { setPreviewGroupId(group.id); setPreviewTemplateKey(null); }}>
                  <Mail size={13} />Vorschau
                </Button>
                <Button size="sm" variant="outline" onClick={() => startRename(group)}>
                  <Pencil size={13} />Umbenennen
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={deletingId === group.id}
                  onClick={() => handleDelete(group)}
                >
                  <Trash2 size={13} />{deletingId === group.id ? "Lösche…" : "Löschen"}
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {previewGroup && (
        <Modal
          title={previewGroup.name}
          eyebrow={`${previewGroup.recipients.length} Empfänger:innen`}
          maxWidth="max-w-2xl"
          onClose={() => setPreviewGroupId(null)}
        >
          <div className="space-y-4">
            <select
              className={`${selectClass} w-full`}
              value={activeTemplateKey ?? ""}
              onChange={(e) => setPreviewTemplateKey(e.target.value || null)}
            >
              <option value="" disabled>Vorlage wählen…</option>
              {templates.map((template) => (
                <option key={template.key} value={template.key}>{template.name}</option>
              ))}
            </select>
            {selectedTemplate ? (
              <>
                <p className="text-[9.5px] uppercase tracking-wider text-brand-muted">
                  Betreff (Beispiel für {exampleRecipient?.name ?? "erste:n Empfänger:in"})
                </p>
                <p className="text-sm text-brand-platinum">{renderedSubject}</p>
                <p className="mt-3 text-[9.5px] uppercase tracking-wider text-brand-muted">Entwurf</p>
                <pre className="whitespace-pre-wrap rounded-md bg-brand-sidebar p-3 text-xs leading-6 text-brand-soft">{renderedBody}</pre>
                <p className="text-xs text-brand-gray">
                  Betreff/Text wurden mit den Daten von {exampleRecipient?.name ?? "der ersten Person"} befüllt — beim Versand geht genau dieser Text unverändert an alle {previewGroup.recipients.length} Empfänger:innen (keine Personalisierung pro Person). Vor dem Senden oben bei Bedarf noch anpassen bzw. hier kopieren.
                </p>
                {bulkSendMessage && (
                  <div className="rounded-lg border border-brand-success/35 bg-brand-success-bg/45 p-3 text-xs text-brand-success-text">
                    {bulkSendMessage}
                  </div>
                )}
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={handleCopy}>
                    {copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "Kopiert" : "Text kopieren"}
                  </Button>
                  <Button size="sm" disabled={bulkSending} onClick={handleBulkSend}>
                    <Mail size={14} />
                    {bulkSending ? "Sende…" : `Jetzt an alle ${previewGroup.recipients.length} senden`}
                  </Button>
                </div>
              </>
            ) : (
              <p className="text-sm text-brand-gray">Vorlage auswählen, um eine Vorschau zu sehen.</p>
            )}
          </div>
        </Modal>
      )}

      {mergeOpen && (
        <Modal title="Gruppen zusammenführen" eyebrow={`${selectedIds.size} ausgewählt`} onClose={() => setMergeOpen(false)}>
          <div className="space-y-4">
            <p className="text-xs text-brand-muted">
              Die Vereinigungsmenge der Empfänger:innen (nach E-Mail-Adresse dedupliziert) wird als neue Gruppe gespeichert oder ersetzt eine bestehende Gruppe.
            </p>
            <div>
              <label className="mb-1 block text-xs text-brand-muted">Name der Zielgruppe</label>
              <Input placeholder="z.B. Q3-Kampagne Süddeutschland" value={mergeName} onChange={(e) => setMergeName(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs text-brand-muted">Bestehende Gruppe überschreiben (optional)</label>
              <select className={`${selectClass} w-full`} value={overwriteId} onChange={(e) => setOverwriteId(e.target.value)}>
                <option value="">Neue Gruppe anlegen</option>
                {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
              </select>
            </div>
            <ErrorBanner message={error} />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setMergeOpen(false)}>Abbrechen</Button>
              <Button disabled={busy || !mergeName.trim()} onClick={handleMerge}>
                {busy ? "Führe zusammen…" : overwriteId ? "Überschreiben" : "Zusammenführen"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
