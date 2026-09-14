"use client";

import { useState } from "react";
import { FileEdit, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { ErrorBanner } from "@/components/crm/error-banner";
import { updateEmailTemplate } from "@/lib/api/queries";
import { invalidateEmailTemplatesCache, useEmailTemplatesCache } from "@/lib/api/hooks";
import type { EmailTemplate } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-[#94A3B8]";
const textareaClass =
  "min-h-40 w-full rounded-md border border-white/10 bg-[#0D1B2E] p-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

/** Verwaltungsansicht fuer die editierbaren Mail-Vorlagen (Auftrag
 * "Mailvorlagen editierbar machen") - Name/Betreff/Text sind jetzt in der DB
 * (Tabelle email_templates) statt hartcodiert, PATCH /email-templates/{key}
 * aendert nur diese drei Felder, `key` bleibt stabil (siehe Backend-
 * Docstring EmailTemplateUpdate), da die Auswahl-Dropdowns in
 * MailingGroupsPanel weiterhin ueber `key` zuordnen. */
export function EmailTemplatesPanel() {
  const { data, isLoading } = useEmailTemplatesCache();
  const templates = data?.data ?? [];
  const [editing, setEditing] = useState<EmailTemplate | null>(null);
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Platzhalter live aus dem GERADE BEARBEITETEN Text extrahiert (nicht aus
  // dem gespeicherten Stand) - zeigt sofort, wenn ein Token entfernt/getippt
  // wird, bevor gespeichert ist.
  const livePlaceholders = Array.from(
    new Set(Array.from(`${subject}\n${body}`.matchAll(/\{(\w+)\}/g)).map((match) => match[1])),
  );

  function openEditor(template: EmailTemplate) {
    setEditing(template);
    setName(template.name);
    setSubject(template.subject);
    setBody(template.body);
    setError(null);
  }

  async function handleSave() {
    if (!editing || !name.trim() || !subject.trim() || !body.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await updateEmailTemplate(editing.key, {
        name: name.trim(),
        subject: subject.trim(),
        body,
      });
      void invalidateEmailTemplatesCache();
      setEditing(null);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Vorlage konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="h-14 animate-pulse rounded-lg bg-[#0D1B2E]" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h2 className="flex items-center gap-2 font-semibold"><FileEdit size={16} />Mail-Vorlagen ({templates.length})</h2>
      <div className="space-y-2">
        {templates.map((template) => (
          <Card key={template.key}>
            <CardContent className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div className="min-w-0">
                <p className="font-semibold">{template.name}</p>
                <p className="mt-1 truncate text-xs text-[#94A3B8]">{template.subject}</p>
                {template.placeholders.length > 0 && (
                  <p className="mt-1 text-[10px] text-[#69A7EA]">
                    Platzhalter: {template.placeholders.map((p) => `{${p}}`).join(", ")}
                  </p>
                )}
              </div>
              <Button size="sm" variant="outline" onClick={() => openEditor(template)}>
                <Pencil size={13} />Bearbeiten
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {editing && (
        <Modal
          title={editing.name}
          eyebrow={`Vorlage · ${editing.key}`}
          maxWidth="max-w-2xl"
          onClose={() => setEditing(null)}
        >
          <div className="space-y-4">
            <div>
              <label className={labelClass}>Name</label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <label className={labelClass}>Betreff</label>
              <Input value={subject} onChange={(e) => setSubject(e.target.value)} />
            </div>
            <div>
              <label className={labelClass}>Text</label>
              <textarea className={textareaClass} value={body} onChange={(e) => setBody(e.target.value)} />
            </div>
            <p className="text-xs text-[#94A3B8]">
              {livePlaceholders.length > 0
                ? `Verwendete Platzhalter: ${livePlaceholders.map((p) => `{${p}}`).join(", ")} - werden beim Versand automatisch aus den Profildaten befüllt.`
                : "Diese Vorlage verwendet aktuell keine Platzhalter."}{" "}
              Wird ein Platzhalter entfernt oder die Schreibweise geändert (z. B. <code>{"{candidate}"}</code> →{" "}
              <code>{"{Kandidat}"}</code>), wird er beim Versand nicht mehr automatisch befüllt.
            </p>
            <ErrorBanner message={error} />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setEditing(null)}>Abbrechen</Button>
              <Button disabled={busy || !name.trim() || !subject.trim() || !body.trim()} onClick={handleSave}>
                {busy ? "Speichere…" : "Speichern"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
