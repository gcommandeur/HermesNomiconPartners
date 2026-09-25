"use client";

import { Download, FileSpreadsheet } from "lucide-react";
import { Button } from "@/components/ui/button";

function escapeCsv(value: unknown) {
  const text = String(value ?? "");
  if (/[",\n;]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

/** "yyyyMMdd-HHmm" statt toISOString(), damit der Dateiname keine
 * Doppelpunkte/"T"/"Z" enthaelt (auf Windows in Dateinamen ungueltig bzw.
 * unschoen). */
function watermarkTimestamp(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return (
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `-${pad(now.getHours())}${pad(now.getMinutes())}`
  );
}

/** Exportiert als CSV-Blob und stoesst den Browser-Download an - wird von
 * ExportActions selbst genutzt, aber auch von einzelnen Zeilen-Export-
 * Buttons (z.B. submission-views.tsx-Tabellenansicht), damit dort nicht die
 * gleiche Blob/Download-Logik dupliziert werden muss.
 *
 * Vertraulichkeits-Kennzeichnung nur ueber einen Zeitstempel-Suffix im
 * DATEINAMEN, bewusst NICHT als zusaetzliche Kommentarzeile im CSV-Inhalt
 * selbst: der Re-Import (services/imports.py::ImportService._parse) liest
 * JEDE Zeile per csv.DictReader als Datensatz - eine angehaengte
 * "# Vertraulich ..."-Zeile wuerde beim Re-Import als kaputte/leere
 * Datenzeile auftauchen (Spaltenzahl passt nicht), statt als Kommentar
 * erkannt zu werden. Kopfzeile bleibt dadurch ohnehin unangetastet. */
export function downloadCsv(filename: string, rows: Record<string, unknown>[]) {
  const headers = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  const csv = [
    headers.join(";"),
    ...rows.map((row) => headers.map((header) => escapeCsv(row[header])).join(";")),
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${filename}_${watermarkTimestamp()}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

export function ExportActions({ filename, rows }: {
  filename: string;
  rows: Record<string, unknown>[];
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="outline" size="sm" onClick={() => downloadCsv(filename, rows)}>
        <Download size={14} />CSV exportieren
      </Button>
      <Button variant="ghost" size="sm" disabled title="XLSX-Export ist strukturell vorgesehen und wird mit Backend/Excel-Adapter aktiviert.">
        <FileSpreadsheet size={14} />XLSX vorbereitet
      </Button>
    </div>
  );
}
