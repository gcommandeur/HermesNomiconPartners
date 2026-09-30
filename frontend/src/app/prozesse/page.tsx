import Link from "next/link";
import { ShieldCheck, Target } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { DemoNotice } from "@/components/crm/demo-notice";
import { SubmissionViews } from "@/components/crm/submission-views";
import { SubmissionCreateModal } from "@/components/crm/submission-create-modal";
import { Button } from "@/components/ui/button";
import { getAllInterviews, getCandidates, getClients, getContacts, getSubmissions } from "@/lib/api/queries";
import type { SubmissionStatus } from "@/lib/api/types";

export const dynamic = "force-dynamic";

const STAGES: SubmissionStatus[] = ["qualification_call", "cv_in", "cv_out", "interview", "offer", "placement", "cancelled"];

export default async function ProcessesPage({
  searchParams,
}: {
  searchParams?: Promise<{ stage?: string; mine?: string }>;
}) {
  const { stage, mine } = (await searchParams) ?? {};
  const initialStage = STAGES.find((value) => value === stage) ?? null;
  const [submissions, candidates, clients, contacts, interviews] = await Promise.all([getSubmissions(), getCandidates(), getClients(), getContacts(), getAllInterviews()]);
  const source = submissions.source === "api" && candidates.source === "api" && clients.source === "api" && contacts.source === "api" ? "api" : "demo";
  return (
    <>
      <PageHeader
        eyebrow="Recruiting-Prozesse"
        title="Prozesse"
        action={
          <div className="flex flex-wrap gap-2">
            <Link href="/prioritaet"><Button size="sm" variant="outline"><Target size={14} />Prioritätsansicht</Button></Link>
            <Link href="/gewaehrleistung"><Button size="sm" variant="outline"><ShieldCheck size={14} />Gewährleistungen</Button></Link>
            <SubmissionCreateModal />
          </div>
        }
      />
      <DemoNotice source={source} />
      <SubmissionViews submissions={submissions.data} candidates={candidates.data} clients={clients.data} contacts={contacts.data} interviews={interviews.data} initialStage={initialStage} initialMineOnly={mine === "1"} />
    </>
  );
}
