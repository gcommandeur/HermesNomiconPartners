"use client";

// NOMICON: Kopfzeile der Ansicht Direct - Pipeline-Wert, erwartete Fees (gewichtet), überfällige
// Nachfassungen, Gewährleistung. Nur echte Werte; fehlende Fees werden gezählt, nicht erfunden.
import useSWR from "swr";
import { Card, CardContent } from "@/components/ui/card";
import { getActiveWarranties } from "@/lib/api/queries";
import { formatEuro, pipelineKpis } from "@/lib/fee-forecast";
import type { CandidateSubmission } from "@/lib/api/types";

export function PipelineKpiStrip({ items }: { items: CandidateSubmission[] }) {
  const { data: warranties } = useSWR("/placements/active-warranties", () => getActiveWarranties(), { revalidateOnFocus: false });
  const kpis = pipelineKpis(items);
  const tiles: { label: string; value: string; hint?: string }[] = [
    { label: "Pipeline-Wert", value: formatEuro(kpis.pipelineValue), hint: "Summe der erwarteten Fees laufender Prozesse" },
    { label: "Erwartete Fees (gewichtet)", value: formatEuro(kpis.expectedWeighted), hint: "Fee × Abschlusswahrscheinlichkeit, nur wo vorhanden" },
    { label: "Nachfassen überfällig", value: String(kpis.overdueFollowUps) },
    { label: "Gewährleistung läuft", value: warranties ? String(warranties.data.length) : "…" },
  ];
  return (
    <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
      {tiles.map((tile) => (
        <div key={tile.label} title={tile.hint}>
          <Card>
          <CardContent className="py-3">
            <p className="text-[10.45px] uppercase tracking-wider text-brand-muted">{tile.label}</p>
            <p className="mt-1 text-xl font-semibold text-brand-text">{tile.value}</p>
            {tile.label.startsWith("Pipeline") && kpis.openFees > 0 && (
              <p className="mt-0.5 text-[10.45px] text-brand-warning">{kpis.openFees} Prozesse mit „Fee offen“</p>
            )}
          </CardContent>
          </Card>
        </div>
      ))}
    </div>
  );
}
