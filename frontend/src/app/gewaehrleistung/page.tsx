import Link from "next/link";
import { ArrowUpRight, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { DemoNotice } from "@/components/crm/demo-notice";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getActiveWarranties, getCandidates, getClients, getSubmissions } from "@/lib/api/queries";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { WarrantyStatus } from "@/lib/api/types";

export const dynamic = "force-dynamic";

const warrantyTone: Record<WarrantyStatus, "green" | "amber" | "red"> = {
  laufend: "green",
  bald_ablaufend: "amber",
  abgelaufen: "red",
};
const warrantyLabel: Record<WarrantyStatus, string> = {
  laufend: "Laufend",
  bald_ablaufend: "Bald ablaufend",
  abgelaufen: "Abgelaufen",
};

export default async function WarrantyOverviewPage() {
  const [placementsResult, submissionsResult, candidatesResult, clientsResult] = await Promise.all([
    getActiveWarranties(),
    getSubmissions(),
    getCandidates(),
    getClients(),
  ]);
  const placements = placementsResult.data;
  const submissionOf = (id: string) => submissionsResult.data.find((item) => item.id === id);
  const candidateName = (id: string | null) => {
    const candidate = id ? candidatesResult.data.find((item) => item.id === id) : undefined;
    return candidate ? `${candidate.first_name} ${candidate.last_name}` : "Kandidat";
  };
  const clientName = (id: string | null) => clientsResult.data.find((item) => item.id === id)?.name ?? "Kanzlei offen";

  return (
    <>
      <PageHeader eyebrow="Recruiting-Prozesse" title="Laufende Gewährleistungen" />
      <DemoNotice source={placementsResult.source} error={placementsResult.error} />
      <div className="mb-5 flex items-center gap-2 rounded-lg border border-white/10 bg-[#0D1B2E]/85 px-3 py-2 text-xs text-[#CBD5E1]">
        <ShieldCheck size={14} />
        Placements mit noch laufender Gewährleistung, sortiert nach dem nächstliegenden Ablaufdatum. Abgelaufene Gewährleistungen werden hier nicht mehr angezeigt.
      </div>
      <div className="space-y-2">
        {placements.map((placement) => {
          const submission = submissionOf(placement.submission_id);
          return (
            <Card key={placement.id}>
              <CardContent className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="font-semibold">{candidateName(submission?.candidate_id ?? null)}</p>
                    <Badge tone={warrantyTone[placement.warranty_status]}>{warrantyLabel[placement.warranty_status]}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-[#94A3B8]">{clientName(submission?.client_company_id ?? null)}</p>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right text-xs text-[#A7ADB7]">
                    <p className="text-[10px] uppercase tracking-wider text-[#94A3B8]">Gewährleistung bis</p>
                    <p className="mt-1 text-sm text-[#F8FAFC]">{formatDate(placement.warranty_end_date)}</p>
                  </div>
                  <div className="text-right text-xs text-[#A7ADB7]">
                    <p className="text-[10px] uppercase tracking-wider text-[#94A3B8]">Fee</p>
                    <p className="mt-1 text-sm text-[#F8FAFC]">{formatCurrency(Number(placement.calculated_fee))}</p>
                  </div>
                  {submission && (
                    <Link
                      href={`/kandidaten/${submission.candidate_id}?from=prozesse`}
                      className="inline-flex items-center gap-1.5 rounded-md border border-[#1F5FA8]/40 bg-[#153A66]/45 px-3 py-1.5 text-xs text-[#c5dcfa] hover:bg-[#153A66]/70"
                    >
                      Profil öffnen <ArrowUpRight size={13} />
                    </Link>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
        {placements.length === 0 && (
          <Card><CardContent className="py-12 text-center text-sm text-[#858b90]">Keine laufenden Gewährleistungen.</CardContent></Card>
        )}
      </div>
    </>
  );
}
