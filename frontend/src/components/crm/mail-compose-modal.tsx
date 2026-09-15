"use client";

import { useEffect, useMemo, useState } from "react";
import { Mail, Paperclip, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { ErrorBanner } from "@/components/crm/error-banner";
import { getDocumentsForOwner, sendMail } from "@/lib/api/queries";
import { useEmailTemplatesCache, useMailAccountsCache } from "@/lib/api/hooks";
import type { DocumentMeta } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-[#94A3B8]";
const selectClass =
  "h-9 w-full rounded-md border border-white/10 bg-[#071426] px-2 text-xs text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";
const textareaClass =
  "min-h-40 w-full rounded-md border border-white/10 bg-[#0D1B2E] p-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

function renderTemplate(text: string, values: Record<string, string>): string {
  return text.replace(/\{(\w+)\}/g, (match, key: string) => values[key] ?? match);
}

/** Senden-Dialog (Auftrag "M365-Postfach-Integration", Compose-UI) -
 * Absender-Postfach + Vorlage (25 aus email_templates) + Betreff/Text
 * (editierbar) + Anhänge (CV-Dokumente ausgeblendet, siehe
 * project_submission_workflow_cv_attachment_guard) -> POST /mail/send.
 * Aufrufbar von Kandidaten-/Kanzlei-Detailseite, Kontakte-Tabelle,
 * Mailing-Gruppen-Panel - jeweils mit dem dort verfügbaren Kontext
 * (Empfänger, Platzhalterwerte, Zuordnung) vorbefüllt. */
export function MailComposeModal({
  onClose,
  onSent,
  toAddress,
  toName,
  documentOwnerType,
  documentOwnerId,
  candidateId,
  clientCompanyId,
  contactPersonId,
  placeholderValues = {},
}: {
  onClose: () => void;
  onSent?: () => void;
  toAddress: string;
  toName?: string;
  /** Fuer den Anhang-Picker - z.B. "candidate"/candidateId, damit nur die
   * Dokumente dieser Person/Kanzlei zur Auswahl stehen. */
  documentOwnerType?: "candidate" | "client";
  documentOwnerId?: string;
  candidateId?: string;
  clientCompanyId?: string;
  contactPersonId?: string;
  /** Werte fuer die Platzhalter-Ersetzung beim Vorlagenwechsel, z.B.
   * {candidate: "Max Muster", role: "Steuerberater:in"} - je nachdem, von
   * welcher Seite aus der Dialog geöffnet wurde. */
  placeholderValues?: Record<string, string>;
}) {
  const { data: accountsResult, isLoading: accountsLoading } = useMailAccountsCache(true);
  const { data: templatesResult, isLoading: templatesLoading } = useEmailTemplatesCache();
  const accounts = useMemo(
    () => (accountsResult?.data ?? []).filter((a) => a.is_active),
    [accountsResult],
  );
  const templates = useMemo(() => templatesResult?.data ?? [], [templatesResult]);

  const [accountId, setAccountId] = useState("");
  const [templateKey, setTemplateKey] = useState("");
  const [subject, setSubject] = useState("");
  const [bodyText, setBodyText] = useState("");
  const [documents, setDocuments] = useState<DocumentMeta[]>([]);
  const [selectedAttachmentIds, setSelectedAttachmentIds] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    if (accounts.length > 0 && !accountId) setAccountId(accounts[0].id);
  }, [accounts, accountId]);

  useEffect(() => {
    if (!documentOwnerType || !documentOwnerId) return;
    void getDocumentsForOwner(documentOwnerType, documentOwnerId).then((result) => {
      // CV-Dokumente werden hier bereits ausgeblendet - die serverseitige
      // Sperre in mail_send.py bleibt die eigentliche Durchsetzung, das ist
      // nur, damit niemand einen abgelehnten Versand erlebt.
      setDocuments(result.data.filter((doc) => doc.document_type !== "cv"));
    });
  }, [documentOwnerType, documentOwnerId]);

  function applyTemplate(key: string) {
    setTemplateKey(key);
    const template = templates.find((t) => t.key === key);
    if (!template) return;
    const values = { contact: toName ?? toAddress, candidate: toName ?? toAddress, ...placeholderValues };
    setSubject(renderTemplate(template.subject, values));
    setBodyText(renderTemplate(template.body, values));
  }

  function toggleAttachment(id: string) {
    setSelectedAttachmentIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSend() {
    if (!subject.trim() || !bodyText.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await sendMail({
        account_id: accountId || null,
        to_address: toAddress,
        to_name: toName ?? null,
        subject: subject.trim(),
        body_text: bodyText,
        attachment_document_ids: Array.from(selectedAttachmentIds),
        candidate_id: candidateId ?? null,
        client_company_id: clientCompanyId ?? null,
        contact_person_id: contactPersonId ?? null,
      });
      setSent(true);
      onSent?.();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Mail konnte nicht gesendet werden.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Mail schreiben" eyebrow={`An ${toName ?? toAddress}`} maxWidth="max-w-2xl" onClose={onClose}>
      {sent ? (
        <div className="space-y-4">
          <p className="text-sm text-[#a9d6b8]">Mail wurde versendet.</p>
          <div className="flex justify-end">
            <Button onClick={onClose}>Schließen</Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {accounts.length > 0 ? (
            <div>
              <label className={labelClass}>Absender-Postfach</label>
              <select
                className={selectClass}
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                disabled={accountsLoading}
              >
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.label} ({account.address})
                  </option>
                ))}
              </select>
            </div>
          ) : (
            // Nicht-Admins duerfen die Postfach-Liste nicht sehen (siehe
            // Backend api/v1/mail_accounts.py) - der Versand laeuft dann
            // ueber MailAccountService.resolve_send_account (persoenliches
            // Standardpostfach), ohne dass hier eine Auswahl noetig ist.
            !accountsLoading && (
              <p className="text-xs text-[#94A3B8]">
                Wird über dein Standardpostfach gesendet (siehe Einstellungen).
              </p>
            )
          )}
          <div>
            <label className={labelClass}>Vorlage (optional)</label>
            <select
              className={selectClass}
              value={templateKey}
              onChange={(e) => applyTemplate(e.target.value)}
              disabled={templatesLoading}
            >
              <option value="">Keine Vorlage / frei schreiben</option>
              {templates.map((template) => (
                <option key={template.key} value={template.key}>
                  {template.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass}>Betreff</label>
            <Input value={subject} onChange={(e) => setSubject(e.target.value)} />
          </div>
          <div>
            <label className={labelClass}>Text</label>
            <textarea className={textareaClass} value={bodyText} onChange={(e) => setBodyText(e.target.value)} />
          </div>
          {documents.length > 0 && (
            <div>
              <label className={labelClass}>
                <Paperclip size={12} className="mr-1 inline" />
                Anhänge
              </label>
              <div className="space-y-1">
                {documents.map((doc) => (
                  <label key={doc.id} className="flex items-center gap-2 text-xs text-[#CBD5E1]">
                    <input
                      type="checkbox"
                      checked={selectedAttachmentIds.has(doc.id)}
                      onChange={() => toggleAttachment(doc.id)}
                    />
                    {doc.filename}
                  </label>
                ))}
              </div>
            </div>
          )}
          <ErrorBanner message={error} />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              Abbrechen
            </Button>
            <Button
              disabled={
                busy ||
                (accounts.length > 0 && !accountId) ||
                !subject.trim() ||
                !bodyText.trim()
              }
              onClick={handleSend}
            >
              <Send size={14} />
              {busy ? "Sende…" : "Senden"}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

/** Kleiner Trigger-Button fuer Detailseiten/Tabellen - haelt den Modal-
 * Open-State selbst, damit Aufrufer nicht jeweils eigenen State brauchen. */
export function MailComposeButton(
  props: Omit<Parameters<typeof MailComposeModal>[0], "onClose"> & { label?: string },
) {
  const [open, setOpen] = useState(false);
  const { label = "Mail schreiben", ...modalProps } = props;
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Mail size={13} />
        {label}
      </Button>
      {open && <MailComposeModal {...modalProps} onClose={() => setOpen(false)} />}
    </>
  );
}
