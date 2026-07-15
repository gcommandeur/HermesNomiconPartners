"use client";

import { Download, FileSpreadsheet } from "lucide-react";
import { Button } from "@/components/ui/button";

function escapeCsv(value: unknown) {
  const text = String(value ?? "");
  if (/[",\n;]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

export function ExportActions({ filename, rows }: {
  filename: string;
  rows: Record<string, unknown>[];
}) {
  const downloadCsv = () => {
    const headers = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
    const csv = [
      headers.join(";"),
      ...rows.map((row) => headers.map((header) => escapeCsv(row[header])).join(";")),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${filename}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="outline" size="sm" onClick={downloadCsv}>
        <Download size={14} />CSV exportieren
      </Button>
      <Button variant="ghost" size="sm" disabled title="XLSX-Export ist strukturell vorgesehen und wird mit Backend/Excel-Adapter aktiviert.">
        <FileSpreadsheet size={14} />XLSX vorbereitet
      </Button>
    </div>
  );
}
