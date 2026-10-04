"use client";

import { useState } from "react";
import { Download, FileSpreadsheet, Upload, X } from "lucide-react";
import { apiDownload, apiPost } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import { Button } from "@/components/ui/button";

type Row = { row_number: number; data: Record<string, unknown>; errors: string[]; duplicate: boolean };
type Preview = { entity: string; columns: string[]; rows: Row[]; valid_count: number; error_count: number; duplicate_count: number; commit_supported: boolean };
type Result = { imported: number; skipped: number; duplicates: number; updated: number; errors: string[] };

export function ImportWizard({ entity, label }: { entity: string; label: string }) {
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Welcher Download-Button gerade laedt (statt document.href, siehe
  // apiDownload()/apiUrl() in lib/api/client.ts: ein roher <a href> auf die
  // Backend-URL kann keinen Authorization-Header mitschicken und schlug mit
  // 401 fehl, seit der Login-Cookie httpOnly ist).
  const [downloading, setDownloading] = useState<string | null>(null);

  async function download(path: string, filename: string, key: string) {
    setDownloading(key);
    setError("");
    try {
      await apiDownload(path, filename);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Download fehlgeschlagen");
    } finally {
      setDownloading(null);
    }
  }

  async function handleFile(file?: File) {
    if (!file) return;
    setBusy(true); setError(""); setResult(null);
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      bytes.forEach((value) => { binary += String.fromCharCode(value); });
      setPreview(await apiPost<Preview>(`/import/${entity}/preview`, { filename: file.name, content_base64: btoa(binary), mapping: {} }));
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Importvorschau fehlgeschlagen");
    } finally { setBusy(false); }
  }

  async function commit() {
    if (!preview) return;
    setBusy(true); setError("");
    try {
      setResult(await apiPost<Result>(`/import/${entity}/commit`, { rows: preview.rows, confirmed: true }));
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Import fehlgeschlagen");
    } finally { setBusy(false); }
  }

  return <>
    <Button variant="outline" onClick={() => setOpen(true)}><Upload size={15} />Import</Button>
    {open && <div className="fixed inset-0 z-[80] grid place-items-center bg-[#020711]/80 p-4 backdrop-blur-sm"><div className="max-h-[90vh] w-full max-w-4xl overflow-auto rounded-xl border bg-brand-surface p-5 shadow-2xl">
      <div className="flex items-start justify-between"><div><p className="text-[9.5px] uppercase tracking-[.2em] text-brand-accent-light">Massupload</p><h2 className="mt-2 text-xl font-semibold">{label} importieren</h2><p className="mt-1 text-xs text-brand-muted">CSV/XLSX bis 10 MB · Vorschau und Bestätigung vor dem Schreiben</p></div><Button variant="ghost" size="icon" onClick={() => setOpen(false)}><X size={18} /></Button></div>
      <div className="mt-5 flex flex-wrap gap-2">
        <label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-md bg-gradient-to-b from-brand-accent to-brand-accent-strong px-4 text-sm font-medium"><FileSpreadsheet size={15} />{busy ? "Wird geprüft..." : "CSV/Excel hochladen"}<input type="file" accept=".csv,.xlsx" className="hidden" onChange={(event) => handleFile(event.target.files?.[0])} /></label>
        <Button
          variant="outline"
          disabled={downloading === "csv-template"}
          onClick={() => download(`/import/${entity}/template?file_format=csv`, `${entity}_template.csv`, "csv-template")}
        >
          <Download size={15} />{downloading === "csv-template" ? "Wird geladen…" : "CSV-Template"}
        </Button>
        <Button
          variant="outline"
          disabled={downloading === "xlsx-template"}
          onClick={() => download(`/import/${entity}/template?file_format=xlsx`, `${entity}_template.xlsx`, "xlsx-template")}
        >
          <Download size={15} />{downloading === "xlsx-template" ? "Wird geladen…" : "Excel-Template"}
        </Button>
        {entity === "candidates" && (
          <Button
            variant="outline"
            disabled={downloading === "candidates-export"}
            onClick={() => download("/import/candidates/export?file_format=xlsx", "candidates_export.xlsx", "candidates-export")}
          >
            <Download size={15} />{downloading === "candidates-export" ? "Wird geladen…" : "Alle Kandidaten exportieren (zum Bearbeiten)"}
          </Button>
        )}
      </div>
      <ErrorBanner message={error} className="mt-4" />
      {preview && <><div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">{[["Importierbar",preview.valid_count],["Fehler",preview.error_count],["Duplikate",preview.duplicate_count]].map(([name,value]) => <div key={String(name)} className="rounded-lg border bg-brand-panel p-3"><p className="text-[9.5px] text-brand-muted">{name}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>)}</div><div className="mt-4 overflow-x-auto rounded-lg border"><table className="w-full text-left text-xs"><thead className="bg-brand-accent-soft"><tr><th className="p-3">Zeile</th><th className="p-3">Vorschau</th><th className="p-3">Status</th></tr></thead><tbody className="divide-y divide-white/10">{preview.rows.slice(0,20).map((row) => <tr key={row.row_number}><td className="p-3">{row.row_number}</td><td className="p-3 text-brand-soft">{Object.values(row.data).slice(0,4).join(" · ")}</td><td className="p-3">{row.errors.length ? row.errors.join("; ") : row.duplicate ? "Duplikat" : "Bereit"}</td></tr>)}</tbody></table></div><div className="mt-4 flex justify-end"><Button disabled={!preview.commit_supported || preview.valid_count === 0 || busy} onClick={commit}>Import bestätigen</Button></div></>}
      {result && <div className="mt-4 rounded-lg border border-brand-success/35 bg-brand-success-bg/35 p-4 text-sm">{result.imported} importiert · {result.updated} aktualisiert · {result.skipped} übersprungen · {result.duplicates} Duplikate</div>}
    </div></div>}
  </>;
}
