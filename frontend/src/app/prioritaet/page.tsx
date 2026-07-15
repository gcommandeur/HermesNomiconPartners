import Link from "next/link";
import { ArrowUpRight, Target } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { DemoNotice } from "@/components/crm/demo-notice";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getCandidates, getClients, getPriorityView } from "@/lib/api/queries";
import { formatCurrency } from "@/lib/utils";

export const dynamic = "force-dynamic";

const closingStatusTone = { hot: "green", warm: "amber", risk: "blue", stop: "red" } as const;
const closingStatusLabel = { hot: "Hot", warm: "Warm", risk: "Risk", stop: "Stop" } as const;

export default async function PriorityViewPage() {
  const [submissionsResult, candidatesResult, clientsResult] = await Promise.all([
    getPriorityView(),
    getCandidates(),
    getClients(),
  ]);
  const submissions = submissionsResult.data;
  const candidateName = (id: string) => {
    const candidate = candidatesResult.data.find((item) => item.id === id);
    return candidate ? `${candidate.first_name} ${candidate.last_name}` : "Kandidat";
  };
  const clientName = (id: string | null) => clientsResult.data.find((item) => item.id === id)?.name ?? "Kanzlei offen";

  return (
    <>
      <PageHeader eyebrow="Prozesse" title="Prioritätsansicht" />
      <DemoNotice source={submissionsResult.source} error={submissionsResult.error} />
      <div className="mb-5 flex items-center gap-2 rounded-lg border border-white/10 bg-[#0D1B2E]/85 px-3 py-2 text-xs text-[#CBD5E1]">
        <Target size={14} />
        Offene Prozesse mit berechnetem Closing-Score, sortiert nach closing_probability × erwartetem Honorar.
      </div>
      <div className="space-y-2">
        {submissions.map((submission) => (
          <Card key={submission.id}>
            <CardContent className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-semibold">{candidateName(submission.candidate_id)}</p>
                  {submission.closing_status && (
                    <Badge tone={closingStatusTone[submission.closing_status]}>
                      {closingStatusLabel[submission.closing_status]} · {submission.closing_probability}%
                    </Badge>
                  )}
                </div>
                <p className="mt-1 text-xs text-[#94A3B8]">{clientName(submission.client_company_id)}</p>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-right text-xs text-[#A7ADB7]">
                  <p className="text-[10px] uppercase tracking-wider text-[#94A3B8]">Erwartetes Honorar</p>
                  <p className="mt-1 text-sm text-[#F8FAFC]">{submission.expected_fee ? formatCurrency(Number(submission.expected_fee)) : "—"}</p>
                </div>
                <Link
                  href={`/kandidaten/${submission.candidate_id}?from=prozesse`}
                  className="inline-flex items-center gap-1.5 rounded-md border border-[#1F5FA8]/40 bg-[#153A66]/45 px-3 py-1.5 text-xs text-[#c5dcfa] hover:bg-[#153A66]/70"
                >
                  Profil öffnen <ArrowUpRight size={13} />
                </Link>
              </div>
            </CardContent>
          </Card>
        ))}
        {submissions.length === 0 && (
          <Card><CardContent className="py-12 text-center text-sm text-[#858b90]">Noch keine bewerteten offenen Prozesse.</CardContent></Card>
        )}
      </div>
    </>
  );
}
