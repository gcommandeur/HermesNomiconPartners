"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, Eye, FileText, Sparkles, TriangleAlert, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { apiDownload, apiFetchBlob, apiPost, apiUpload } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import { formatDate } from "@/lib/utils";
import { brand } from "@/lib/brand";
import type { CvExtractionSuggestion, DocumentMeta } from "@/lib/api/types";

const CV_FIELD_LABELS: Record<keyof Omit<CvExtractionSuggestion, "source_is_agency_profile">, string> = {
  first_name: "Vorname",
  last_name: "Nachname",
  email: "E-Mail",
  postal_code: "PLZ",
  city: "Ort",
  phone: "Telefon",
  job_title: "Rolle",
  qualification: "Qualifikation",
  ausbildung_titel: "Ausbildung/Weiterbildung",
};

/** Zeigt an, welche Kandidatenfelder gerade automatisch aus einem frisch
 * hochgeladenen CV uebernommen wurden (siehe Backend
 * CandidateService.auto_fill_from_cv) - nur Felder, die beim Kandidaten
 * vorher leer waren, werden je befuellt, ein vorhandener Wert wird nie
 * ueberschrieben. Rein informativ: das Uebernehmen ist zu diesem Zeitpunkt
 * bereits serverseitig passiert (Nutzer-Vorgabe: "soll beim Hochladen sofort
 * entstehen", keine manuelle Bestaetigung pro Feld mehr noetig). */
function CvExtractionPanel({ suggestion, onDismiss }: {
  suggestion: CvExtractionSuggestion;
  onDismiss: () => void;
}) {
  const fieldEntries = (Object.keys(CV_FIELD_LABELS) as (keyof typeof CV_FIELD_LABELS)[])
    .map((key) => ({ key, value: suggestion[key] }))
    .filter((entry): entry is { key: keyof typeof CV_FIELD_LABELS; value: string } => Boolean(entry.value));

  if (fieldEntries.length === 0) return null;

  return (
    <Card className="border-brand-accent/30 bg-brand-accent-soft/50">
      <CardContent>
        <div className="flex items-center gap-2 text-sm font-semibold text-brand-platinum">
          <Sparkles size={15} />Aus dem CV übernommen
        </div>
        {suggestion.source_is_agency_profile && (
          <p className="mt-2 rounded bg-brand-warning/10 px-2 py-1.5 text-[10.45px] text-brand-warning">
            Dieses Dokument enthält den {brand.companyName}-Briefkopf (anonymisiertes Bewerberprofil) — Adresse/Telefon
            wurden deshalb nicht übernommen, nur Rolle/Qualifikation.
          </p>
        )}
        <div className="mt-3 space-y-1.5">
          {fieldEntries.map(({ key, value }) => (
            <div key={key} className="flex items-center gap-2 text-xs text-brand-soft">
              <span className="w-40 shrink-0 text-brand-muted">{CV_FIELD_LABELS[key]}</span>
              <span>{value}</span>
            </div>
          ))}
        </div>
        <div className="mt-3 flex justify-end">
          <Button size="sm" variant="outline" onClick={onDismiss}>Ausblenden</Button>
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
          <div className="flex flex-col items-center gap-3 rounded-lg border border-white/10 bg-brand-surface/60 py-16 text-sm text-brand-muted">
            <FileText size={28} />
            Keine Vorschau verfügbar für diesen Dateityp.
          </div>
        )}
        {kind !== "none" && <ErrorBanner message={error} />}
        {kind !== "none" && !error && !blobUrl && (
          <div className="flex items-center justify-center rounded-lg border border-white/10 bg-brand-surface/60 py-16 text-sm text-brand-muted">
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
  const [dragActive, setDragActive] = useState(false);
  const dragCounter = useRef(0);

  function handlePickFile() {
    fileInputRef.current?.click();
  }

  async function uploadFile(file: File) {
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("owner_type", ownerType);
      formData.append("owner_id", ownerId);
      formData.append("document_type", documentType);
      formData.append("file", file);
      const uploaded = await apiUpload<DocumentMeta>("/documents/upload", formData);
      // Beim manuellen CV-Upload eines Kandidaten werden leere Felder (PLZ,
      // Rolle, ...) serverseitig sofort aus dem CV befuellt (siehe
      // CandidateService.auto_fill_from_cv) - fehlschlagende Extraktion
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
      router.refresh();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Upload fehlgeschlagen.");
    } finally {
      setUploading(false);
    }
  }

  async function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    await uploadFile(file);
  }

  // Drag-Counter statt eines einfachen Booleans: onDragLeave feuert schon
  // beim Ueberqueren jedes Kind-Elements der Drop-Zone (nicht nur beim
  // endgueltigen Verlassen), ein simples true/false wuerde die Hervorhebung
  // dadurch schon beim Drueberziehen ueber ein Kind-Element voreilig
  // zuruecksetzen.
  function handleDragEnter(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (!event.dataTransfer.types.includes("Files")) return;
    dragCounter.current += 1;
    setDragActive(true);
  }

  function handleDragLeave(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragCounter.current = Math.max(0, dragCounter.current - 1);
    if (dragCounter.current === 0) setDragActive(false);
  }

  function handleDragOver(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
  }

  async function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragCounter.current = 0;
    setDragActive(false);
    const file = event.dataTransfer.files?.[0];
    if (!file || uploading) return;
    await uploadFile(file);
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
      <div
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className={`flex items-center justify-between rounded-lg border p-3 text-xs transition-colors ${
          dragActive
            ? "border-brand-accent bg-brand-accent/10 text-brand-platinum"
            : "border-white/10 bg-brand-surface/75 text-brand-muted"
        }`}
      >
        <span>{dragActive ? "Datei hier ablegen…" : "Dateien werden lokal im CRM-Speicher abgelegt - oder hier ablegen (Drag & Drop)."}</span>
        <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileSelected} />
        <Button size="sm" variant="outline" onClick={handlePickFile} disabled={uploading}>
          <Upload size={14} />
          {uploading ? "Wird hochgeladen…" : "Datei hochladen"}
        </Button>
      </div>
      <ErrorBanner message={error} />
      {cvSuggestion && ownerType === "candidate" && (
        <CvExtractionPanel suggestion={cvSuggestion} onDismiss={() => setCvSuggestion(null)} />
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
              <FileText size={16} className="shrink-0 text-brand-platinum" />
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
                <p className="mt-1 text-xs text-brand-muted">
                  {document.document_type}
                  {document.size_bytes ? ` · ${Math.round(document.size_bytes / 1024)} KB` : ""}
                </p>
              </div>
            </button>
            <div className="flex items-center gap-3">
              <span className="text-xs text-brand-gray">{formatDate(document.created_at)}</span>
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
          <CardContent className="py-12 text-center text-sm text-brand-gray">
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
