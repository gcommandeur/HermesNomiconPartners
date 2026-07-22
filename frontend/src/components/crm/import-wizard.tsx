"use client";

import { useState } from "react";
import { Download, FileSpreadsheet, Upload, X } from "lucide-react";
import { apiBaseUrl, apiPost } from "@/lib/api/client";
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
    {open && <div className="fixed inset-0 z-[80] grid place-items-center bg-[#020711]/80 p-4 backdrop-blur-sm"><div className="max-h-[90vh] w-full max-w-4xl overflow-auto rounded-xl border bg-[#0D1B2E] p-5 shadow-2xl">
      <div className="flex items-start justify-between"><div><p className="text-[10px] uppercase tracking-[.2em] text-[#69A7EA]">Massupload</p><h2 className="mt-2 text-xl font-semibold">{label} importieren</h2><p className="mt-1 text-xs text-[#94A3B8]">CSV/XLSX bis 10 MB · Vorschau und Bestätigung vor dem Schreiben</p></div><Button variant="ghost" size="icon" onClick={() => setOpen(false)}><X size={18} /></Button></div>
      <div className="mt-5 flex flex-wrap gap-2"><label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-md bg-gradient-to-b from-[#1F5FA8] to-[#153A66] px-4 text-sm font-medium"><FileSpreadsheet size={15} />{busy ? "Wird geprüft..." : "CSV/Excel hochladen"}<input type="file" accept=".csv,.xlsx" className="hidden" onChange={(event) => handleFile(event.target.files?.[0])} /></label>{apiBaseUrl && <><a href={`${apiBaseUrl}/import/${entity}/template?file_format=csv`} className="inline-flex h-10 items-center gap-2 rounded-md border px-4 text-sm text-[#CBD5E1]"><Download size={15} />CSV-Template</a><a href={`${apiBaseUrl}/import/${entity}/template?file_format=xlsx`} className="inline-flex h-10 items-center gap-2 rounded-md border px-4 text-sm text-[#CBD5E1]"><Download size={15} />Excel-Template</a>{entity === "candidates" && <a href={`${apiBaseUrl}/import/candidates/export?file_format=xlsx`} className="inline-flex h-10 items-center gap-2 rounded-md border px-4 text-sm text-[#CBD5E1]"><Download size={15} />Alle Kandidaten exportieren (zum Bearbeiten)</a>}</>}</div>
      <ErrorBanner message={error} className="mt-4" />
      {preview && <><div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">{[["Importierbar",preview.valid_count],["Fehler",preview.error_count],["Duplikate",preview.duplicate_count]].map(([name,value]) => <div key={String(name)} className="rounded-lg border bg-[#12243A] p-3"><p className="text-[10px] text-[#94A3B8]">{name}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>)}</div><div className="mt-4 overflow-x-auto rounded-lg border"><table className="w-full text-left text-xs"><thead className="bg-[#102A4C]"><tr><th className="p-3">Zeile</th><th className="p-3">Vorschau</th><th className="p-3">Status</th></tr></thead><tbody className="divide-y divide-white/10">{preview.rows.slice(0,20).map((row) => <tr key={row.row_number}><td className="p-3">{row.row_number}</td><td className="p-3 text-[#CBD5E1]">{Object.values(row.data).slice(0,4).join(" · ")}</td><td className="p-3">{row.errors.length ? row.errors.join("; ") : row.duplicate ? "Duplikat" : "Bereit"}</td></tr>)}</tbody></table></div><div className="mt-4 flex justify-end"><Button disabled={!preview.commit_supported || preview.valid_count === 0 || busy} onClick={commit}>Import bestätigen</Button></div></>}
      {result && <div className="mt-4 rounded-lg border border-[#4f8a68]/35 bg-[#244d38]/35 p-4 text-sm">{result.imported} importiert · {result.updated} aktualisiert · {result.skipped} übersprungen · {result.duplicates} Duplikate</div>}
    </div></div>}
  </>;
}
