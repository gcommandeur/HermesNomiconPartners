"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, Eye, FileText, Sparkles, TriangleAlert, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { Input } from "@/components/ui/input";
import { apiDownload, apiFetchBlob, apiPatch, apiPost, apiUpload } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import { formatDate } from "@/lib/utils";
import type { CvExtractionSuggestion, DocumentMeta } from "@/lib/api/types";

const CV_FIELD_LABELS: Record<keyof Omit<CvExtractionSuggestion, "source_is_agency_profile">, string> = {
  postal_code: "PLZ",
  city: "Ort",
  phone: "Telefon",
  job_title: "Rolle",
  qualification: "Qualifikation",
  ausbildung_titel: "Ausbildung/Weiterbildung",
};

/** Zeigt aus einem gerade hochgeladenen CV automatisch erkannte Feldvorschlaege
 * (Phase M, Punkt 2) - nur Felder, die beim Kandidaten aktuell leer sind
 * (siehe Backend CandidateService.suggest_cv_fields). Der Nutzer waehlt pro
 * Feld einzeln, ob er den Vorschlag uebernimmt, und kann den Wert vor dem
 * Uebernehmen noch korrigieren - nichts wird automatisch gespeichert. */
function CvExtractionPanel({ candidateId, suggestion, onApplied, onDismiss }: {
  candidateId: string;
  suggestion: CvExtractionSuggestion;
  onApplied: () => void;
  onDismiss: () => void;
}) {
  const fieldEntries = (Object.keys(CV_FIELD_LABELS) as (keyof typeof CV_FIELD_LABELS)[])
    .map((key) => ({ key, value: suggestion[key] }))
    .filter((entry): entry is { key: keyof typeof CV_FIELD_LABELS; value: string } => Boolean(entry.value));

  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(fieldEntries.map(({ key, value }) => [key, value])),
  );
  const [accepted, setAccepted] = useState<Record<string, boolean>>(
    Object.fromEntries(fieldEntries.map(({ key }) => [key, true])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (fieldEntries.length === 0) return null;

  async function handleApply() {
    setBusy(true);
    setError(null);
    try {
      const payload = Object.fromEntries(
        fieldEntries.filter(({ key }) => accepted[key]).map(({ key }) => [key, values[key]]),
      );
      if (Object.keys(payload).length > 0) {
        await apiPatch(`/candidates/${candidateId}`, payload);
      }
      onApplied();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Übernehmen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="border-[#1F5FA8]/30 bg-[#102A4C]/50">
      <CardContent>
        <div className="flex items-center gap-2 text-sm font-semibold text-[#D8DADF]">
          <Sparkles size={15} />Aus dem CV erkannt
        </div>
        {suggestion.source_is_agency_profile && (
          <p className="mt-2 rounded bg-[#F0B429]/10 px-2 py-1.5 text-[11px] text-[#F0B429]">
            Dieses Dokument enthält den Commandeur-Briefkopf (anonymisiertes Bewerberprofil) — Adresse/Telefon
            wurden deshalb nicht übernommen, nur Rolle/Qualifikation.
          </p>
        )}
        <div className="mt-3 space-y-2">
          {fieldEntries.map(({ key }) => (
            <label key={key} className="flex items-center gap-2 text-xs text-[#CBD5E1]">
              <input
                type="checkbox"
                checked={accepted[key] ?? false}
                onChange={(event) => setAccepted((current) => ({ ...current, [key]: event.target.checked }))}
              />
              <span className="w-40 shrink-0 text-[#94A3B8]">{CV_FIELD_LABELS[key]}</span>
              <Input
                value={values[key] ?? ""}
                onChange={(event) => setValues((current) => ({ ...current, [key]: event.target.value }))}
                disabled={!accepted[key]}
              />
            </label>
          ))}
        </div>
        {error && <p className="mt-2 text-xs text-red-300">{error}</p>}
        <div className="mt-3 flex justify-end gap-2">
          <Button size="sm" variant="outline" onClick={onDismiss}>Verwerfen</Button>
          <Button size="sm" onClick={handleApply} disabled={busy}>
            {busy ? "Übernehme…" : "Felder übernehmen"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

const PDF_TYPES = new Set(["application/pdf"]);
const IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"]);

function previewKind(document: DocumentMeta): "pdf" | "image" | "none" {
  const type = document.content_type ?? "";
  if (PDF_TYPES.has(type) || document.filename.toLowerCase().endsWith(".pdf")) return "pdf";
  if (IMAGE_TYPES.has(type) || /\.(png|jpe?g|gif|webp|svg)$/i.test(document.filename)) return "image";
  return "none";
}

function DocumentPreviewModal({ document, onClose, onDownload }: {
  document: DocumentMeta;
  onClose: () => void;
  onDownload: () => void;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const kind = previewKind(document);

  useEffect(() => {
    if (kind === "none") return;
    let objectUrl: string | null = null;
    let cancelled = false;
    apiFetchBlob(`/documents/${document.id}/download`)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      })
      .catch((exception) => {
        if (!cancelled) {
          setError(exception instanceof Error ? exception.message : "Vorschau fehlgeschlagen.");
        }
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [document.id, kind]);

  return (
    <Modal title={document.filename} eyebrow="Dokumentvorschau" maxWidth="max-w-3xl" onClose={onClose}>
      <div className="space-y-4">
        {kind === "none" && (
          <div className="flex flex-col items-center gap-3 rounded-lg border border-white/10 bg-[#0D1B2E]/60 py-16 text-sm text-[#94A3B8]">
            <FileText size={28} />
            Keine Vorschau verfügbar für diesen Dateityp.
          </div>
        )}
        {kind !== "none" && <ErrorBanner message={error} />}
        {kind !== "none" && !error && !blobUrl && (
          <div className="flex items-center justify-center rounded-lg border border-white/10 bg-[#0D1B2E]/60 py-16 text-sm text-[#94A3B8]">
            Lädt…
          </div>
        )}
        {kind === "pdf" && blobUrl && (
          <iframe src={blobUrl} title={document.filename} className="h-[70vh] w-full rounded-lg border border-white/10 bg-white" />
        )}
        {kind === "image" && blobUrl && (
          // eslint-disable-next-line @next/next/no-img-element -- Blob-URL, next/image kann keine blob: URLs optimieren
          <img src={blobUrl} alt={document.filename} className="max-h-[70vh] w-full rounded-lg object-contain" />
        )}
        <div className="flex justify-end">
          <Button size="sm" onClick={onDownload}><Download size={14} />Herunterladen</Button>
        </div>
      </div>
    </Modal>
  );
}

interface DocumentPanelProps {
  ownerType: "candidate" | "client" | "submission" | "placement" | "fee";
  ownerId: string;
  documentType: string;
  documents: DocumentMeta[];
}

export function DocumentPanel({ ownerType, ownerId, documentType, documents }: DocumentPanelProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [previewDocument, setPreviewDocument] = useState<DocumentMeta | null>(null);
  const [cvSuggestion, setCvSuggestion] = useState<CvExtractionSuggestion | null>(null);

  function handlePickFile() {
    fileInputRef.current?.click();
  }

  async function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("owner_type", ownerType);
      formData.append("owner_id", ownerId);
      formData.append("document_type", documentType);
      formData.append("file", file);
      const uploaded = await apiUpload<DocumentMeta>("/documents/upload", formData);
      router.refresh();
      // Beim manuellen CV-Upload eines Kandidaten automatisch strukturierte
      // Felder vorschlagen (Phase M, Punkt 2) - fehlschlagende Extraktion
      // (z.B. kein Anthropic-Key konfiguriert) darf den Upload selbst nicht
      // als fehlgeschlagen erscheinen lassen, daher separat abgefangen.
      if (ownerType === "candidate" && documentType === "cv") {
        try {
          const suggestion = await apiPost<CvExtractionSuggestion>(
            `/candidates/${ownerId}/cv-extraction`,
            { document_id: uploaded.id },
          );
          setCvSuggestion(suggestion);
        } catch {
          setCvSuggestion(null);
        }
      }
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Upload fehlgeschlagen.");
    } finally {
      setUploading(false);
    }
  }

  async function handleDownload(document: DocumentMeta) {
    setDownloadingId(document.id);
    setError(null);
    try {
      await apiDownload(`/documents/${document.id}/download`, document.filename);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Download fehlgeschlagen.");
    } finally {
      setDownloadingId(null);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between rounded-lg border border-white/10 bg-[#0D1B2E]/75 p-3 text-xs text-[#94A3B8]">
        <span>Dateien werden lokal im CRM-Speicher abgelegt.</span>
        <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileSelected} />
        <Button size="sm" variant="outline" onClick={handlePickFile} disabled={uploading}>
          <Upload size={14} />
          {uploading ? "Wird hochgeladen…" : "Datei hochladen"}
        </Button>
      </div>
      <ErrorBanner message={error} />
      {cvSuggestion && ownerType === "candidate" && (
        <CvExtractionPanel
          candidateId={ownerId}
          suggestion={cvSuggestion}
          onApplied={() => { setCvSuggestion(null); router.refresh(); }}
          onDismiss={() => setCvSuggestion(null)}
        />
      )}
      {documents.map((document) => (
        <Card key={document.id}>
          <CardContent className="flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={() => setPreviewDocument(document)}
              className="flex min-w-0 flex-1 items-center gap-3 text-left"
              title="Vorschau öffnen"
            >
              <FileText size={16} className="shrink-0 text-[#D8DADF]" />
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="truncate font-semibold hover:underline">{document.filename}</p>
                  {document.has_generic_filename && (
                    <span title="Generischer Dateiname, ggf. umbenennen">
                      <Badge tone="amber" className="gap-1">
                        <TriangleAlert size={11} />Generischer Dateiname
                      </Badge>
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-[#94A3B8]">
                  {document.document_type}
                  {document.size_bytes ? ` · ${Math.round(document.size_bytes / 1024)} KB` : ""}
                </p>
              </div>
            </button>
            <div className="flex items-center gap-3">
              <span className="text-xs text-[#8b9196]">{formatDate(document.created_at)}</span>
              <Button size="sm" variant="ghost" onClick={() => setPreviewDocument(document)} title="Vorschau">
                <Eye size={14} />
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleDownload(document)}
                disabled={downloadingId === document.id}
              >
                <Download size={14} />
                {downloadingId === document.id ? "…" : "Herunterladen"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
      {documents.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-[#858b90]">
            Noch keine Dokumente hinterlegt.
          </CardContent>
        </Card>
      )}
      {previewDocument && (
        <DocumentPreviewModal
          document={previewDocument}
          onClose={() => setPreviewDocument(null)}
          onDownload={() => handleDownload(previewDocument)}
        />
      )}
    </div>
  );
}
