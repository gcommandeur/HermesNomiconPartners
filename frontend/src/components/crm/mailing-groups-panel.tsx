"use client";

import { useMemo, useState } from "react";
import { Check, Combine, Copy, Mail, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { apiPatch, apiPost } from "@/lib/api/client";
import { invalidateMailingGroupsCache, useMailingGroupsCache } from "@/lib/api/hooks";
import type { EmailTemplate, MailingGroup } from "@/lib/api/types";

function renderTemplate(text: string, values: Record<string, string>): string {
  return text.replace(/\{(\w+)\}/g, (match, key: string) => values[key] ?? match);
}

const selectClass = "h-9 rounded-md border border-white/10 bg-[#071426] px-2 text-xs text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

export function MailingGroupsPanel({ templates }: { templates: EmailTemplate[] }) {
  const { data, isLoading } = useMailingGroupsCache();
  const groups = useMemo(() => data?.data ?? [], [data]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [previewGroupId, setPreviewGroupId] = useState<string | null>(null);
  const [previewTemplateKey, setPreviewTemplateKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeName, setMergeName] = useState("");
  const [overwriteId, setOverwriteId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

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

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="h-16 animate-pulse rounded-lg bg-[#0D1B2E]" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {message && <div className="rounded-lg border border-[#4f8a68]/35 bg-[#244d38]/45 p-3 text-xs text-[#a9d6b8]">{message}</div>}
      {error && <div className="rounded-lg border border-red-400/25 bg-red-950/30 p-3 text-xs text-red-200">{error}</div>}

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
        <Card><CardContent className="py-12 text-center text-sm text-[#858b90]">
          Noch keine Mailing-Gruppen gespeichert — auf Kandidaten-/Kanzlei-/Kontaktprofilen oder im Geo Mapping über &quot;Für Mailing nutzen&quot; anlegen.
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
                <div>
                  <p className="font-semibold">{group.name}</p>
                  <p className="mt-1 text-xs text-[#94A3B8]">{group.recipients.length} Empfänger:innen</p>
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
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {previewGroup && (
        <Modal
          title={previewGroup.name}
          eyebrow={`${previewGroup.recipients.length} Empfänger:innen — nur Entwurf`}
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
                <p className="text-[10px] uppercase tracking-wider text-[#94A3B8]">
                  Betreff (Beispiel für {exampleRecipient?.name ?? "erste:n Empfänger:in"})
                </p>
                <p className="text-sm text-[#D8DADF]">{renderedSubject}</p>
                <p className="mt-3 text-[10px] uppercase tracking-wider text-[#94A3B8]">Entwurf</p>
                <pre className="whitespace-pre-wrap rounded-md bg-[#071426] p-3 text-xs leading-6 text-[#CBD5E1]">{renderedBody}</pre>
                <p className="text-xs text-[#8b9196]">
                  Nur Textvorschau zum Kopieren — kein automatischer Versand. Beim tatsächlichen Versand an alle {previewGroup.recipients.length} Empfänger:innen würde die Vorlage individuell personalisiert.
                </p>
                <Button size="sm" onClick={handleCopy}>
                  {copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "Kopiert" : "Text kopieren"}
                </Button>
              </>
            ) : (
              <p className="text-sm text-[#858b90]">Vorlage auswählen, um eine Vorschau zu sehen.</p>
            )}
          </div>
        </Modal>
      )}

      {mergeOpen && (
        <Modal title="Gruppen zusammenführen" eyebrow={`${selectedIds.size} ausgewählt`} onClose={() => setMergeOpen(false)}>
          <div className="space-y-4">
            <p className="text-xs text-[#94A3B8]">
              Die Vereinigungsmenge der Empfänger:innen (nach E-Mail-Adresse dedupliziert) wird als neue Gruppe gespeichert oder ersetzt eine bestehende Gruppe.
            </p>
            <div>
              <label className="mb-1 block text-xs text-[#94A3B8]">Name der Zielgruppe</label>
              <Input placeholder="z.B. Q3-Kampagne Süddeutschland" value={mergeName} onChange={(e) => setMergeName(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs text-[#94A3B8]">Bestehende Gruppe überschreiben (optional)</label>
              <select className={`${selectClass} w-full`} value={overwriteId} onChange={(e) => setOverwriteId(e.target.value)}>
                <option value="">Neue Gruppe anlegen</option>
                {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
              </select>
            </div>
            {error && <div className="rounded-lg border border-red-400/25 bg-red-950/30 p-3 text-xs text-red-200">{error}</div>}
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
