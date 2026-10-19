"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { mutate } from "swr";
import { PageHeader } from "@/components/crm/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MailComposeModal } from "@/components/crm/mail-compose-modal";
import { approveAiProposal, getAiProposals, rejectAiProposal } from "@/lib/api/queries";
import type { AiProposal, AiProposalKind } from "@/lib/api/types";

const KIND_LABELS: Record<AiProposalKind, string> = {
  note: "Notiz",
  task: "Aufgabe",
  mail_draft: "Mail-Entwurf",
};
const STATUS_LABELS = { pending: "offen", approved: "freigegeben", rejected: "abgelehnt" } as const;
const textareaClass =
  "min-h-28 w-full rounded-md border border-white/10 bg-brand-surface p-3 text-sm text-brand-text outline-none focus:border-brand-accent";
const labelClass = "mb-1 block text-xs text-brand-muted";

function targetHref(proposal: AiProposal): string | null {
  if (!proposal.target_id) return null;
  if (proposal.target_type === "candidate") return `/kandidaten/${proposal.target_id}`;
  if (proposal.target_type === "client") return `/kunden/${proposal.target_id}`;
  return null;
}

function ProposalCard({
  proposal,
  onChanged,
  onOpenMail,
}: {
  proposal: AiProposal;
  onChanged: () => void;
  onOpenMail: (proposal: AiProposal, payload: AiProposal["payload"]) => void;
}) {
  const [payload, setPayload] = useState(proposal.payload);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const pending = proposal.status === "pending";
  const href = targetHref(proposal);

  const set = (key: keyof AiProposal["payload"], value: string) =>
    setPayload((current) => ({ ...current, [key]: value }));

  async function decide(approve: boolean) {
    setBusy(true);
    setMessage(null);
    try {
      if (approve) {
        const result = await approveAiProposal(proposal.id, payload);
        if (proposal.kind === "mail_draft") onOpenMail(proposal, result.payload);
      } else {
        await rejectAiProposal(proposal.id);
      }
      onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Aktion fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="font-medium">
              {KIND_LABELS[proposal.kind]}
              {proposal.target_label && (
                <>
                  {" · "}
                  {href ? (
                    <Link href={href} className="text-brand-accent-light underline">
                      {proposal.target_label}
                    </Link>
                  ) : (
                    proposal.target_label
                  )}
                </>
              )}
            </p>
            <p className="text-xs text-brand-muted">
              Vorschlag von Claude für {proposal.created_by_name ?? "—"} ·{" "}
              {new Date(proposal.created_at).toLocaleString("de-DE")} · {STATUS_LABELS[proposal.status]}
            </p>
          </div>
        </div>

        {proposal.kind === "note" && (
          <div>
            <label className={labelClass}>Text der Notiz</label>
            <textarea
              className={textareaClass}
              disabled={!pending}
              value={payload.text ?? ""}
              onChange={(e) => set("text", e.target.value)}
            />
          </div>
        )}
        {proposal.kind === "task" && (
          <div className="space-y-3">
            <div>
              <label className={labelClass}>Titel</label>
              <Input disabled={!pending} value={payload.title ?? ""} onChange={(e) => set("title", e.target.value)} />
            </div>
            <div>
              <label className={labelClass}>Beschreibung</label>
              <textarea
                className={textareaClass}
                disabled={!pending}
                value={payload.description ?? ""}
                onChange={(e) => set("description", e.target.value)}
              />
            </div>
            {payload.due_at && <p className="text-xs text-brand-muted">Fällig: {new Date(payload.due_at).toLocaleString("de-DE")}</p>}
          </div>
        )}
        {proposal.kind === "mail_draft" && (
          <div className="space-y-3">
            <p className="text-xs text-brand-muted">
              An: {proposal.recipient_email ?? "keine E-Mail-Adresse hinterlegt"} – es wird nichts automatisch
              gesendet. Nach der Freigabe öffnet sich das Mail-Fenster, das Senden machst du selbst.
            </p>
            <div>
              <label className={labelClass}>Betreff</label>
              <Input disabled={!pending} value={payload.subject ?? ""} onChange={(e) => set("subject", e.target.value)} />
            </div>
            <div>
              <label className={labelClass}>Text</label>
              <textarea
                className={textareaClass}
                disabled={!pending}
                value={payload.body ?? ""}
                onChange={(e) => set("body", e.target.value)}
              />
            </div>
          </div>
        )}

        {message && <p className="text-xs text-red-300">{message}</p>}
        {pending && (
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={busy || (proposal.kind === "mail_draft" && !proposal.recipient_email)}
              onClick={() => void decide(true)}
            >
              {proposal.kind === "mail_draft" ? "Freigeben & Mail öffnen" : "Freigeben & anlegen"}
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => void decide(false)}>
              Ablehnen
            </Button>
          </div>
        )}
        {!pending && proposal.result_entity_type && (
          <p className="text-xs text-brand-muted">Angelegt: {proposal.result_entity_type === "note" ? "Notiz" : "Aufgabe"}.</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function ClaudeVorschlaegePage() {
  const [tab, setTab] = useState<"pending" | "done">("pending");
  const [items, setItems] = useState<AiProposal[] | null>(null);
  const [mail, setMail] = useState<{ proposal: AiProposal; payload: AiProposal["payload"] } | null>(null);

  const load = useCallback(async () => {
    const result = await getAiProposals();
    setItems(result.data);
    void mutate("/ai-proposals/summary");
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const shown = (items ?? []).filter((item) => (tab === "pending" ? item.status === "pending" : item.status !== "pending"));

  return (
    <>
      <PageHeader eyebrow="Schreibtisch" title="Claude-Vorschläge" />
      <p className="mb-5 max-w-3xl text-sm text-brand-muted">
        Claude bereitet Notizen, Aufgaben und Mail-Entwürfe vor – angelegt oder gesendet wird nichts, bevor du es
        hier freigibst. Du kannst jeden Text vorher ändern. Mails sendest du immer selbst.
      </p>
      <div className="mb-4 flex gap-2">
        <Button size="sm" variant={tab === "pending" ? "default" : "outline"} onClick={() => setTab("pending")}>
          Offen
        </Button>
        <Button size="sm" variant={tab === "done" ? "default" : "outline"} onClick={() => setTab("done")}>
          Entschieden
        </Button>
      </div>
      <div className="space-y-3">
        {items !== null && shown.length === 0 && (
          <p className="text-sm text-brand-muted">{tab === "pending" ? "Keine offenen Vorschläge." : "Noch nichts entschieden."}</p>
        )}
        {shown.map((proposal) => (
          <ProposalCard
            key={proposal.id}
            proposal={proposal}
            onChanged={() => void load()}
            onOpenMail={(p, payload) => setMail({ proposal: p, payload })}
          />
        ))}
      </div>
      {mail && mail.proposal.recipient_email && (
        <MailComposeModal
          toAddress={mail.proposal.recipient_email}
          toName={mail.proposal.target_label ?? undefined}
          candidateId={mail.proposal.target_type === "candidate" ? (mail.proposal.target_id ?? undefined) : undefined}
          clientCompanyId={mail.proposal.target_type === "client" ? (mail.proposal.target_id ?? undefined) : undefined}
          contactPersonId={mail.proposal.target_type === "contact" ? (mail.proposal.target_id ?? undefined) : undefined}
          documentOwnerType={mail.proposal.target_type === "candidate" ? "candidate" : mail.proposal.target_type === "client" ? "client" : undefined}
          documentOwnerId={mail.proposal.target_id ?? undefined}
          initialSubject={mail.payload.subject ?? ""}
          initialBody={mail.payload.body ?? ""}
          onClose={() => setMail(null)}
        />
      )}
    </>
  );
}
