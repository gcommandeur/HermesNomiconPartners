import Link from "next/link";
import { ShieldCheck, Target } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { DemoNotice } from "@/components/crm/demo-notice";
import { SubmissionViews } from "@/components/crm/submission-views";
import { SubmissionCreateModal } from "@/components/crm/submission-create-modal";
import { Button } from "@/components/ui/button";
import { getCandidates, getClients, getContacts, getSubmissions } from "@/lib/api/queries";

export const dynamic = "force-dynamic";

export default async function ProcessesPage() {
  const [submissions, candidates, clients, contacts] = await Promise.all([getSubmissions(), getCandidates(), getClients(), getContacts()]);
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
            <SubmissionCreateModal candidates={candidates.data} clients={clients.data} />
          </div>
        }
      />
      <DemoNotice source={source} />
      <SubmissionViews submissions={submissions.data} candidates={candidates.data} clients={clients.data} contacts={contacts.data} />
    </>
  );
}
