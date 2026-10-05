"use client";

import { useCallback, useEffect, useState } from "react";
import { Archive, Download, ShieldCheck, ShieldOff } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCurrentUser } from "@/lib/api/hooks";
import {
  decidePresentationRemoval,
  downloadPresentationFile,
  getPresentationRecord,
  getPresentationRecords,
  getPresentationRemovalRequests,
  requestPresentationRemoval,
  setPresentationRetention,
  verifyPresentationRecord,
} from "@/lib/api/queries";
import type {
  PresentationRecordDetail,
  PresentationRecordItem,
  PresentationRemovalRequest,
  PresentationVerifyResult,
} from "@/lib/api/types";
import { formatDateTime } from "@/lib/utils";

const labelClass = "mb-1 block text-xs text-brand-muted";

function formatSize(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

/** Vorstellungs-Archiv (Administration): Nachweis, was bei einer Vorstellung an die Kanzlei
 * gegangen ist. Nur fuer Admins; das Backend antwortet Nicht-Admins mit 404. */
export default function PresentationArchivePage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const myEmail = meData?.data.email ?? null;
  const [items, setItems] = useState<PresentationRecordItem[]>([]);
  const [total, setTotal] = useState(0);
  const [numberFilter, setNumberFilter] = useState("");
  const [requests, setRequests] = useState<PresentationRemovalRequest[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PresentationRecordDetail | null>(null);
  const [verify, setVerify] = useState<PresentationVerifyResult | null>(null);
  const [retention, setRetention] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [list, pending] = await Promise.all([
      getPresentationRecords({ candidateNumber: numberFilter.trim() || undefined }),
      getPresentationRemovalRequests(),
    ]);
    setItems(list.data.items);
    setTotal(list.data.total);
    setRequests(pending.data.filter((request) => request.status === "pending"));
  }, [numberFilter]);

  useEffect(() => {
    if (!isAdmin) return;
    void load();
  }, [isAdmin, load]);

  async function open(recordId: string) {
    setError(null);
    setMessage(null);
    setVerify(null);
    if (openId === recordId) {
      setOpenId(null);
      setDetail(null);
      return;
    }
    const result = await getPresentationRecord(recordId);
    setOpenId(recordId);
    setDetail(result.data);
    setRetention(result.data?.retention_until ?? "");
  }

  async function run(action: () => Promise<void>) {
    setError(null);
    setMessage(null);
    try {
      await action();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Aktion fehlgeschlagen.");
    }
  }

  if (meLoading) {
    return <div className="h-16 animate-pulse rounded-lg bg-brand-surface" />;
  }

  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow="Administration" title="Vorstellungs-Archiv" />
        <Card>
          <CardContent className="flex items-center gap-3 text-sm text-brand-muted">
            <ShieldOff size={18} /> Nur für Admins zugänglich.
          </CardContent>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader eyebrow="Administration" title="Vorstellungs-Archiv" />
      <p className="mb-5 max-w-3xl text-sm text-brand-muted">
        Nachweis für Honorar-Streitfälle: Bei jeder Vorstellung an eine Kanzlei wird beim Versand festgehalten, was
        hinausgegangen ist (Empfänger, Text, Anhänge mit Prüfsumme). Die Einträge sind unveränderlich und nur für Admins
        sichtbar. Entfernen geht erst nach Ablauf der Aufbewahrungsfrist, mit Begründung und Freigabe durch einen
        zweiten Admin. Für Vorstellungen vor Einführung des Archivs gibt es keinen Eintrag.
      </p>

      {requests.length > 0 && (
        <Card className="mb-5">
          <CardContent className="space-y-3">
            <p className="text-sm font-semibold">Offene Entfernen-Anträge ({requests.length})</p>
            {requests.map((request) => {
              const own = request.requested_by === myEmail;
              return (
                <div key={request.id} className="flex flex-wrap items-start justify-between gap-3 border-t border-white/10 pt-3">
                  <div className="min-w-0 text-xs text-brand-soft">
                    <p>
                      {request.client_name ?? "Kanzlei"} · Nr. {request.candidate_number ?? "—"} · beantragt von{" "}
                      {request.requested_by} am {formatDateTime(request.created_at)}
                    </p>
                    <p className="mt-1 text-brand-muted">Begründung: {request.reason}</p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      disabled={own}
                      title={own ? "Die Freigabe muss ein anderer Admin erteilen." : undefined}
                      onClick={() =>
                        void run(async () => {
                          await decidePresentationRemoval(request.id, true);
                          setMessage("Eintrag und Dateien wurden entfernt.");
                          setOpenId(null);
                          setDetail(null);
                          await load();
                        })
                      }
                    >
                      Freigeben und entfernen
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        void run(async () => {
                          await decidePresentationRemoval(request.id, false);
                          await load();
                        })
                      }
                    >
                      Ablehnen
                    </Button>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      <div className="mb-4 flex max-w-xs items-end gap-2">
        <div className="flex-1">
          <label className={labelClass}>Kandidatennummer</label>
          <Input value={numberFilter} onChange={(e) => setNumberFilter(e.target.value)} placeholder="z. B. 4711" />
        </div>
      </div>
      {message && <p className="mb-3 text-sm text-brand-success-text">{message}</p>}
      {error && <p className="mb-3 text-sm text-brand-danger-soft">{error}</p>}
      <p className="mb-3 text-xs text-brand-muted">{total} Eintrag/Einträge</p>

      <div className="space-y-3">
        {items.length === 0 && <p className="text-sm text-brand-muted">Keine Einträge.</p>}
        {items.map((item) => (
          <Card key={item.id}>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">
                    <Archive size={14} className="mr-1.5 inline text-brand-muted" />
                    {item.client_name ?? "Kanzlei unbekannt"} · Nr. {item.candidate_number ?? "—"}
                    {item.candidate_name ? ` (${item.candidate_name})` : ""}
                  </p>
                  <p className="text-xs text-brand-muted">
                    {formatDateTime(item.sent_at)} · von {item.sent_by_email ?? "unbekannt"} an{" "}
                    {item.recipient_emails.join(", ")} · {item.file_count} Anhang/Anhänge
                    {item.retention_until ? ` · aufbewahren bis ${item.retention_until}` : " · keine Frist gesetzt"}
                    {item.removal_requested ? " · Entfernen beantragt" : ""}
                  </p>
                  <p className="mt-1 text-xs text-brand-soft">Betreff: {item.mail_subject}</p>
                </div>
                <Button size="sm" variant="outline" onClick={() => void run(() => open(item.id))}>
                  {openId === item.id ? "Schließen" : "Details"}
                </Button>
              </div>

              {openId === item.id && detail && (
                <div className="space-y-4 border-t border-white/10 pt-3 text-xs">
                  <div>
                    <p className={labelClass}>Mailtext</p>
                    <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md border border-white/10 bg-brand-surface p-3 text-brand-text">
                      {detail.mail_body_text}
                    </pre>
                  </div>
                  {detail.profile_text_snapshot && (
                    <div>
                      <p className={labelClass}>Profiltext zum Versandzeitpunkt</p>
                      <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-white/10 bg-brand-surface p-3 text-brand-text">
                        {detail.profile_text_snapshot}
                      </pre>
                    </div>
                  )}
                  <div className="space-y-2">
                    <p className={labelClass}>Versendete Dateien</p>
                    {detail.files.length === 0 && <p className="text-brand-muted">Kein Anhang (nur Text versendet).</p>}
                    {detail.files.map((file) => {
                      const check = verify?.files.find((entry) => entry.index === file.index);
                      return (
                        <div key={file.index} className="flex flex-wrap items-center justify-between gap-2">
                          <div className="min-w-0">
                            <p className="text-brand-text">
                              {file.filename} · {formatSize(file.size)}
                            </p>
                            <p className="break-all font-mono text-[10.45px] text-brand-muted">SHA-256 {file.sha256}</p>
                            {check && (
                              <p className={check.ok ? "text-brand-success-text" : "text-brand-danger-soft"}>
                                {check.ok
                                  ? "Prüfsumme stimmt überein."
                                  : check.missing
                                    ? "Datei fehlt im Speicher!"
                                    : "ACHTUNG: Prüfsumme weicht ab!"}
                              </p>
                            )}
                          </div>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => void run(() => downloadPresentationFile(item.id, file.index, file.filename))}
                          >
                            <Download size={13} /> Herunterladen
                          </Button>
                        </div>
                      );
                    })}
                    {detail.files.length > 0 && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          void run(async () => {
                            const result = await verifyPresentationRecord(item.id);
                            setVerify(result.data);
                          })
                        }
                      >
                        <ShieldCheck size={13} /> Prüfsumme prüfen
                      </Button>
                    )}
                  </div>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <label className={labelClass}>Aufbewahren bis (setzt der Admin)</label>
                      <div className="flex gap-2">
                        <Input type="date" value={retention} onChange={(e) => setRetention(e.target.value)} />
                        <Button
                          size="sm"
                          onClick={() =>
                            void run(async () => {
                              const updated = await setPresentationRetention(item.id, retention || null);
                              setDetail(updated);
                              setMessage("Aufbewahrungsfrist gespeichert.");
                              await load();
                            })
                          }
                        >
                          Speichern
                        </Button>
                      </div>
                    </div>
                    <div>
                      <label className={labelClass}>Entfernen beantragen (nach Fristablauf)</label>
                      <div className="flex gap-2">
                        <Input
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          placeholder="Begründung (mind. 10 Zeichen)"
                        />
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={detail.removal_requested}
                          onClick={() =>
                            void run(async () => {
                              await requestPresentationRemoval(item.id, reason);
                              setReason("");
                              setMessage("Antrag gestellt. Ein anderer Admin muss ihn freigeben.");
                              await load();
                            })
                          }
                        >
                          Beantragen
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}
