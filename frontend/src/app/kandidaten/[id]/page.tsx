import { notFound } from "next/navigation";
import { ArrowLeft, Clock3, Ghost, Mail, MapPin, Phone } from "lucide-react";
import Link from "next/link";
import {
  getActivitiesForCandidate,
  getCandidate,
  getClients,
  getDocumentsForOwner,
  getNotesForCandidate,
  getSubmissions,
  getTasksForCandidate,
} from "@/lib/api/queries";
import { StatusPill } from "@/components/crm/status-pill";
import { DemoNotice } from "@/components/crm/demo-notice";
import { CandidateMatchingPanel } from "@/components/crm/candidate-matching-panel";
import { AnonymousProfilePanel } from "@/components/crm/anonymous-profile-panel";
import { DocumentPanel } from "@/components/crm/document-panel";
import { CandidateEditModal } from "@/components/crm/candidate-create-modal";
import { AddToMailingButton } from "@/components/crm/add-to-mailing-button";
import { RegisterRecentCandidate } from "@/components/crm/register-recent-candidate";
import { CandidateSubmissionStages } from "@/components/crm/candidate-submission-stages";
import { CandidateProcessLog } from "@/components/crm/candidate-process-log";
import { NotesPanel } from "@/components/crm/notes-panel";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDate, rolleLabel } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function CandidateDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams?: Promise<{ from?: string; tab?: string }>;
}) {
  const { id } = await params;
  const { from, tab } = (await searchParams) ?? {};
  const backLink = from === "prozesse"
    ? { href: "/prozesse", label: "Zurück zu Prozesse" }
    : { href: "/kandidaten", label: "Zur Kandidatenliste" };
  const [result, submissionsResult, clientsResult, activitiesResult, tasksResult, documentsResult, notesResult] = await Promise.all([
    getCandidate(id),
    getSubmissions(),
    getClients(),
    getActivitiesForCandidate(id),
    getTasksForCandidate(id),
    getDocumentsForOwner("candidate", id),
    getNotesForCandidate(id),
  ]);
  const candidate = result.data;
  if (!candidate) notFound();

  const submissions = submissionsResult.data.filter((item) => item.candidate_id === candidate.id);
  const activities = activitiesResult.data;
  const tasks = tasksResult.data;
  const documents = documentsResult.data;
  const notes = notesResult.data;
  const clientName = (clientId: string | null) => clientId ? (clientsResult.data.find((client) => client.id === clientId)?.name ?? "Kanzlei") : "Kanzlei offen";
  const anonymousProfile = candidate.short_profile ?? [
    `${candidate.job_title ?? "Kandidat/in"} mit Schwerpunkt ${candidate.summary ?? "Steuern / Beratung"}.`,
    `Region: ${candidate.city ?? candidate.postal_code ?? "offen"}.`,
    `Gehaltsrahmen: ${candidate.salary_expectation ?? "nach Absprache"}.`,
    `Verfügbarkeit: ${candidate.notice_period ?? "nach Absprache"}.`,
  ].join("\n");
  const tabs = ["Übersicht", "Anonymes Profil", "Notizen", "Matching", "CV-Outs", "Timeline", "Aufgaben", "Dokumente"];
  // Erlaubt einen direkten Link auf einen bestimmten Tab (z.B. "?tab=Dokumente"
  // nach dem Anlegen eines Kandidaten, siehe candidate-create-modal.tsx) -
  // faellt auf "Übersicht" zurueck, wenn der Wert fehlt oder ungueltig ist.
  const initialTab = tab && tabs.includes(tab) ? tab : "Übersicht";

  return (
    <>
      <RegisterRecentCandidate
        id={candidate.id}
        label={`${candidate.candidate_number ? `${candidate.candidate_number} · ` : ""}${candidate.first_name} ${candidate.last_name}`}
      />
      <Link href={backLink.href} className="mb-5 inline-flex items-center gap-2 text-xs text-[#94A3B8] hover:text-[#D8DADF]"><ArrowLeft size={14} />{backLink.label}</Link>
      <DemoNotice source={result.source} />
      <div className="mb-6 flex flex-col justify-between gap-4 border-b border-white/10 pb-6 sm:flex-row sm:items-end">
        <div>
          <div className="mb-3 flex items-center gap-3">
            <StatusPill status={candidate.status} />
            {candidate.has_ghosting_history && <Badge tone="red" className="gap-1"><Ghost size={12} />Ghosting-Historie</Badge>}
            <span className="text-xs text-[#8b9196]">Aktualisiert {formatDate(candidate.updated_at)}</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-[-.035em]">{candidate.first_name} {candidate.last_name}</h1>
          <p className="mt-2 text-sm text-[#CBD5E1]">{candidate.job_title ?? "Rolle offen"} · {candidate.city ?? candidate.postal_code ?? "Region offen"}</p>
          {/* Normalisierte Rollen-Kategorien (models/enums.py::Rolle) -
           * durchsuchbare Ergaenzung zu job_title oben (Freitext aus dem
           * CV), deshalb prominent direkt im Kopfbereich statt versteckt
           * in einem Tab. */}
          {candidate.rollen && candidate.rollen.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {candidate.rollen.map((rolle) => <Badge key={rolle} tone="blue">{rolleLabel(rolle)}</Badge>)}
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-4 text-xs text-[#CBD5E1]">
          {candidate.email && <span className="flex items-center gap-1.5"><Mail size={14} />{candidate.email}</span>}
          {candidate.phone && <span className="flex items-center gap-1.5"><Phone size={14} />{candidate.phone}</span>}
          {candidate.email && (
            <AddToMailingButton
              recipient={{ kind: "candidate", id: candidate.id, name: `${candidate.first_name} ${candidate.last_name}`, email: candidate.email }}
            />
          )}
          <CandidateEditModal candidate={candidate} />
        </div>
      </div>

      <CandidateProcessLog candidateId={candidate.id} />

      {submissions.length > 0 && (
        <div className="mb-6 space-y-4 border-b border-white/10 pb-6">
          <CandidateSubmissionStages submissions={submissions} clients={clientsResult.data} />
        </div>
      )}

      <Tabs defaultValue={initialTab}>
        <TabsList className="scrollbar-subtle mb-5 overflow-x-auto">
          {tabs.map((tab) => <TabsTrigger key={tab} value={tab}>{tab}</TabsTrigger>)}
        </TabsList>
        <TabsContent value="Übersicht">
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.3fr_.7fr]">
            <Card><CardContent><h2 className="font-semibold">Profil</h2><p className="mt-4 text-sm leading-7 text-[#CBD5E1]">{candidate.summary ?? "Noch keine Zusammenfassung hinterlegt."}</p>
              <div className="mt-6 grid grid-cols-1 gap-5 border-t border-white/10 pt-5 sm:grid-cols-2">
                {[["Rolle", candidate.job_title], ["Gehaltswunsch", candidate.salary_expectation], ["Kündigungsfrist", candidate.notice_period], ["Region", `${candidate.postal_code ?? ""} ${candidate.city ?? ""}`.trim()], ["Anrede", candidate.anrede === "frau" ? "Frau" : candidate.anrede === "herr" ? "Herr" : candidate.anrede === "divers" ? "Divers" : null], ["Empfohlen von", candidate.referred_by]].map(([label, value]) => <div key={label}><p className="text-[10px] font-semibold uppercase tracking-wider text-[#92979c]">{label}</p><p className="mt-1.5 text-sm">{value || "—"}</p></div>)}
              </div>
              <div className="mt-6 grid grid-cols-1 gap-5 border-t border-white/10 pt-5 sm:grid-cols-2">
                {[["Ausbildung / Weiterbildung", candidate.ausbildung_titel], ["Aktuelles Umfeld", [candidate.aktuelles_umfeld_kanzleityp, candidate.aktuelles_umfeld_kanzleigroesse].filter(Boolean).join(" · ")], ["Remote-/Teilzeit-Wünsche", candidate.remote_teilzeit_wuensche], ["Passender Kanzleityp", candidate.passender_kanzleityp]].map(([label, value]) => <div key={label}><p className="text-[10px] font-semibold uppercase tracking-wider text-[#92979c]">{label}</p><p className="mt-1.5 text-sm">{value || "—"}</p></div>)}
              </div>
              {candidate.fachliche_schwerpunkte && candidate.fachliche_schwerpunkte.length > 0 && (
                <div className="mt-6 border-t border-white/10 pt-5">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[#92979c]">Fachliche Schwerpunkte</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {candidate.fachliche_schwerpunkte.map((item) => <span key={item} className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-[#D8DADF]">{item}</span>)}
                  </div>
                </div>
              )}
              {candidate.edv_kenntnisse && candidate.edv_kenntnisse.length > 0 && (
                <div className="mt-6 border-t border-white/10 pt-5">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[#92979c]">EDV-Kenntnisse</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {candidate.edv_kenntnisse.map((item) => <span key={item} className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-[#D8DADF]">{item}</span>)}
                  </div>
                </div>
              )}
              {candidate.berufliche_stationen && candidate.berufliche_stationen.length > 0 && (
                <div className="mt-6 border-t border-white/10 pt-5">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[#92979c]">Berufliche Stationen</p>
                  <div className="space-y-1.5">
                    {candidate.berufliche_stationen.map((station, index) => (
                      <p key={index} className="text-sm text-[#CBD5E1]">{station.kanzleityp} · {station.kanzleigroesse} · {station.dauer_jahre} Jahre</p>
                    ))}
                  </div>
                </div>
              )}
              {candidate.freitext_notizen && (
                <div className="mt-6 border-t border-white/10 pt-5">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[#92979c]">Freitextnotizen</p>
                  <p className="mt-1.5 text-sm text-[#CBD5E1]">{candidate.freitext_notizen}</p>
                </div>
              )}
              {(candidate.wechselgrund || (candidate.no_gos && candidate.no_gos.length > 0)) && (
                <div className="mt-6 rounded-lg border border-[#F0B429]/25 bg-[#F0B429]/5 p-4">
                  <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-[#F0B429]">Nur intern — nie in ausgehende Dokumente</p>
                  {candidate.wechselgrund && <div className="mb-3"><p className="text-[10px] font-semibold uppercase tracking-wider text-[#92979c]">Wechselgrund</p><p className="mt-1.5 text-sm text-[#CBD5E1]">{candidate.wechselgrund}</p></div>}
                  {candidate.no_gos && candidate.no_gos.length > 0 && (
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-[#92979c]">No-Gos</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {candidate.no_gos.map((item) => <span key={item} className="rounded-full border border-[#F0B429]/25 bg-[#F0B429]/10 px-2.5 py-1 text-xs text-[#F0B429]">{item}</span>)}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent></Card>
            <Card><CardContent><h2 className="font-semibold">Nächster Schritt</h2><div className="mt-4 rounded-lg bg-[#102A4C]/60 p-4 text-sm text-[#D8DADF]">{candidate.next_step ?? "Kontakt aufnehmen"}</div><div className="mt-5 flex items-center gap-2 text-xs text-[#747a80]"><MapPin size={14} />{candidate.city ?? "Keine Region"} · {candidate.postal_code ?? "keine PLZ"}</div></CardContent></Card>
          </div>
        </TabsContent>
        <TabsContent value="Anonymes Profil">
          <AnonymousProfilePanel candidateId={candidate.id} initialText={anonymousProfile} />
        </TabsContent>
        <TabsContent value="Notizen">
          <NotesPanel candidateId={candidate.id} initialNotes={notes} />
        </TabsContent>
        <TabsContent value="Matching">
          <CandidateMatchingPanel candidateId={candidate.id} />
        </TabsContent>
        <TabsContent value="CV-Outs">
          <div className="space-y-3">
            {submissions.map((item) => <Card key={item.id}><CardContent className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center"><div><p className="font-semibold">{clientName(item.client_company_id)}</p><p className="mt-1 text-xs text-[#777d83]">Vorgestellt {formatDate(item.submitted_at)} · {item.next_step ?? "Nächster Schritt offen"}</p></div><div className="flex items-center gap-3"><StatusPill status={item.status} /><span className="text-xs text-[#D8DADF]">{item.expected_fee ? `${item.expected_fee.toLocaleString("de-DE")} €` : ""}</span></div></CardContent></Card>)}
            {submissions.length === 0 && <Card><CardContent className="py-12 text-center text-sm text-[#858b90]">Noch keine CV-Outs.</CardContent></Card>}
          </div>
        </TabsContent>
        <TabsContent value="Timeline">
          <div className="space-y-2">
            {activities.map((activity) => (
              <Card key={activity.id}>
                <CardContent className="flex items-start gap-3">
                  <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-[#102A4C] text-[#D8DADF]"><Clock3 size={14} /></span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-semibold">{activity.subject}</p>
                      <span className="text-xs text-[#8b9196]">{formatDate(activity.occurred_at)}</span>
                    </div>
                    {activity.details && <p className="mt-1 text-xs text-[#94A3B8]">{activity.details}</p>}
                    <span className="mt-2 inline-block rounded bg-[#12243A] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[#94A3B8]">{activity.activity_type.replace(/_/g, " ")}</span>
                  </div>
                </CardContent>
              </Card>
            ))}
            {activities.length === 0 && <Card><CardContent className="py-12 text-center text-sm text-[#858b90]">Noch keine Aktivitäten für diesen Kandidaten.</CardContent></Card>}
          </div>
        </TabsContent>
        <TabsContent value="Aufgaben">
          <div className="space-y-2">
            {tasks.map((task) => (
              <Card key={task.id}>
                <CardContent className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                  <div>
                    <p className="font-semibold">{task.title}</p>
                    {task.description && <p className="mt-1 text-xs text-[#94A3B8]">{task.description}</p>}
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusPill status={task.priority} />
                    <StatusPill status={task.status} />
                    <span className="text-xs text-[#8b9196]">{task.due_at ? formatDate(task.due_at) : "kein Termin"}</span>
                  </div>
                </CardContent>
              </Card>
            ))}
            {tasks.length === 0 && <Card><CardContent className="py-12 text-center text-sm text-[#858b90]">Keine offenen Aufgaben für diesen Kandidaten.</CardContent></Card>}
          </div>
        </TabsContent>
        <TabsContent value="Dokumente">
          <DocumentPanel ownerType="candidate" ownerId={candidate.id} documentType="cv" documents={documents} />
        </TabsContent>
      </Tabs>
    </>
  );
}
