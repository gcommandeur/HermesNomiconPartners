import { notFound } from "next/navigation";
import { ArrowLeft, Ghost, Mail, MapPin, Phone } from "lucide-react";
import Link from "next/link";
import {
  getActivitiesForCandidate,
  getAssignableUsers,
  getCandidate,
  getCandidateComments,
  getCandidateHistory,
  getClientsByIds,
  getDocumentsForOwner,
  getNotesForCandidate,
  getSubmissionsForCandidate,
  getTasksForCandidate,
} from "@/lib/api/queries";
import { StatusPill } from "@/components/crm/status-pill";
import { DemoNotice } from "@/components/crm/demo-notice";
import { CandidateMatchingPanel } from "@/components/crm/candidate-matching-panel";
import { AnonymousProfilePanel } from "@/components/crm/anonymous-profile-panel";
import { DocumentPanel } from "@/components/crm/document-panel";
import { CandidateEditModal } from "@/components/crm/candidate-create-modal";
import { AddToMailingButton } from "@/components/crm/add-to-mailing-button";
import { CvOutCampaignButton } from "@/components/crm/cv-out-campaign-modal";
import { MailComposeButton } from "@/components/crm/mail-compose-modal";
import { RegisterRecentCandidate } from "@/components/crm/register-recent-candidate";
import { CandidateSubmissionStages } from "@/components/crm/candidate-submission-stages";
import { CandidateSequencesPanel } from "@/components/crm/candidate-sequences-panel";
import { CandidateProcessLog } from "@/components/crm/candidate-process-log";
import { CandidateTimeline } from "@/components/crm/candidate-timeline";
import { CandidateRollenUnbestaetigtHint } from "@/components/crm/candidate-rollen-unbestaetigt-hint";
import { NotesPanel } from "@/components/crm/notes-panel";
import { StaffingCandidatePanel } from "@/components/crm/staffing-candidate-panel"; // NOMICON
import { CustomFieldsPanel } from "@/components/crm/custom-fields-panel";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { abschlussartLabel, formatDate, rechtsgebietLabel, rolleLabel } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function CandidateDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams?: Promise<{ from?: string; tab?: string; back?: string }>;
}) {
  const { id } = await params;
  const { from, tab, back } = (await searchParams) ?? {};
  // `back` (voller Pfad+Query, URL-kodiert) hat Vorrang vor dem aelteren
  // `from`-Mechanismus - gesetzt von jedem Einstiegspunkt, der von einer
  // gefilterten Kandidatenliste aus navigiert (siehe topbar.tsx::goTo), damit
  // "Zur Kandidatenliste" den kompletten Filter-/Such-/Sortier-/Seiten-
  // Zustand wiederherstellt statt auf einer leeren Standardliste zu landen.
  // `from=prozesse` bleibt als Fallback bestehen, wo (noch) kein `back`
  // mitgegeben wird.
  const backLink = back
    ? { href: decodeURIComponent(back), label: "Zur Kandidatenliste" }
    : from === "prozesse"
      ? { href: "/prozesse", label: "Zurück zu Prozesse" }
      : { href: "/kandidaten", label: "Zur Kandidatenliste" };
  // Nur die Prozesse DIESES Kandidaten und danach nur die darin referenzierten
  // Kanzleien laden - vorher wurden hier ALLE Prozesse und ALLE Kanzleien
  // (mehrere tausend, seitenweise nacheinander) geladen, nur um ein paar
  // Kanzleinamen anzuzeigen (~10s Ladezeit).
  const [result, submissionsResult, activitiesResult, tasksResult, documentsResult, notesResult, historyResult, commentsResult, usersResult] = await Promise.all([
    getCandidate(id),
    getSubmissionsForCandidate(id),
    getActivitiesForCandidate(id),
    getTasksForCandidate(id),
    getDocumentsForOwner("candidate", id),
    getNotesForCandidate(id),
    getCandidateHistory(id),
    getCandidateComments(id),
    getAssignableUsers(),
  ]);
  const candidate = result.data;
  if (!candidate) notFound();

  const submissions = submissionsResult.data.filter((item) => item.candidate_id === candidate.id);
  const clients = await getClientsByIds(
    submissions.flatMap((item) => (item.client_company_id ? [item.client_company_id] : [])),
  );
  const activities = activitiesResult.data;
  const tasks = tasksResult.data;
  const documents = documentsResult.data;
  const notes = notesResult.data;
  const history = historyResult.data;
  const comments = commentsResult.data;
  const users = usersResult.data;
  const clientName = (clientId: string | null) => clientId ? (clients.find((client) => client.id === clientId)?.name ?? "Kanzlei") : "Kanzlei offen";
  const anonymousProfile = candidate.short_profile ?? [
    `${candidate.job_title ?? "Kandidat/in"} mit Schwerpunkt ${candidate.summary ?? "Steuern / Beratung"}.`,
    `Region: ${candidate.city ?? candidate.postal_code ?? "offen"}.`,
    `Gehaltsrahmen: ${candidate.salary_expectation ?? "nach Absprache"}.`,
    `Verfügbarkeit: ${candidate.notice_period ?? "nach Absprache"}.`,
  ].join("\n");
  const tabs = ["Übersicht", "Anonymes Profil", "Notizen", "Matching", "CV-Outs", "Timeline", "Aufgaben", "Dokumente", "Überlassung" /* NOMICON */];
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
      <Link href={backLink.href} className="mb-5 inline-flex items-center gap-2 text-xs text-brand-muted hover:text-brand-platinum"><ArrowLeft size={14} />{backLink.label}</Link>
      <DemoNotice source={result.source} />
      <div className="mb-6 flex flex-col justify-between gap-4 border-b border-white/10 pb-6 sm:flex-row sm:items-end">
        <div>
          <div className="mb-3 flex items-center gap-3">
            <StatusPill status={candidate.status} />
            {candidate.has_ghosting_history && <Badge tone="red" className="gap-1"><Ghost size={12} />Ghosting-Historie</Badge>}
            <span className="text-xs text-brand-gray">Aktualisiert {formatDate(candidate.updated_at)}</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-[-.035em]">{candidate.first_name} {candidate.last_name}</h1>
          <p className="mt-2 text-sm text-brand-soft">{candidate.job_title ?? "Rolle offen"} · {candidate.city ?? candidate.postal_code ?? "Region offen"}</p>
          {/* Normalisierte Rollen-Kategorien (models/enums.py::Rolle) -
           * durchsuchbare Ergaenzung zu job_title oben (Freitext aus dem
           * CV), deshalb prominent direkt im Kopfbereich statt versteckt
           * in einem Tab. */}
          {candidate.rollen && candidate.rollen.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {candidate.rollen.map((rolle) => <Badge key={rolle} tone="blue">{rolleLabel(rolle)}</Badge>)}
            </div>
          )}
          <CandidateRollenUnbestaetigtHint candidate={candidate} />
          {/* Strukturierte Abschlussart(en) (models/enums.py::Abschlussart) -
           * macht ausbildung_titel (Freitext) filterbar, siehe
           * abschluesse-Filter in candidates-table.tsx. */}
          {candidate.abschluesse && candidate.abschluesse.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {candidate.abschluesse.map((abschlussart) => (
                <Badge key={abschlussart} tone="gray">{abschlussartLabel(abschlussart)}</Badge>
              ))}
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-4 text-xs text-brand-soft">
          {candidate.email && <span className="flex items-center gap-1.5"><Mail size={14} />{candidate.email}</span>}
          {candidate.phone && <span className="flex items-center gap-1.5"><Phone size={14} />{candidate.phone}</span>}
          {candidate.email && (
            <AddToMailingButton
              recipient={{ kind: "candidate", id: candidate.id, name: `${candidate.first_name} ${candidate.last_name}`, email: candidate.email }}
            />
          )}
          {candidate.email && (
            <MailComposeButton
              toAddress={candidate.email}
              toName={`${candidate.first_name} ${candidate.last_name}`}
              candidateId={candidate.id}
              documentOwnerType="candidate"
              documentOwnerId={candidate.id}
              placeholderValues={{ candidate: `${candidate.first_name} ${candidate.last_name}` }}
            />
          )}
          <CvOutCampaignButton
            candidateId={candidate.id}
            candidateName={`${candidate.first_name} ${candidate.last_name}`}
          />
          <CandidateEditModal candidate={candidate} />
        </div>
      </div>

      <CandidateProcessLog candidateId={candidate.id} />

      {submissions.length > 0 && (
        <div className="mb-6 space-y-4 border-b border-white/10 pb-6">
          <CandidateSubmissionStages submissions={submissions} clients={clients} />
        </div>
      )}

      <CandidateSequencesPanel candidateId={candidate.id} />

      <CustomFieldsPanel entityType="candidate" entityId={candidate.id} initialValues={candidate.custom_fields} />

      <Tabs defaultValue={initialTab}>
        <TabsList className="scrollbar-subtle mb-5 overflow-x-auto">
          {tabs.map((tab) => <TabsTrigger key={tab} value={tab}>{tab}</TabsTrigger>)}
        </TabsList>
        <TabsContent value="Übersicht">
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.3fr_.7fr]">
            <Card><CardContent><h2 className="font-semibold">Profil</h2><p className="mt-4 text-sm leading-7 text-brand-soft">{candidate.summary ?? "Noch keine Zusammenfassung hinterlegt."}</p>
              <div className="mt-6 grid grid-cols-1 gap-5 border-t border-white/10 pt-5 sm:grid-cols-2">
                {[["Rolle", candidate.job_title], ["Gehaltswunsch", candidate.salary_expectation], ["Kündigungsfrist", candidate.notice_period], ["Region", `${candidate.postal_code ?? ""} ${candidate.city ?? ""}`.trim()], ["Anrede", candidate.anrede === "frau" ? "Frau" : candidate.anrede === "herr" ? "Herr" : candidate.anrede === "divers" ? "Divers" : null], ["Empfohlen von", candidate.referred_by]].map(([label, value]) => <div key={label}><p className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">{label}</p><p className="mt-1.5 text-sm">{value || "—"}</p></div>)}
              </div>
              <div className="mt-6 grid grid-cols-1 gap-5 border-t border-white/10 pt-5 sm:grid-cols-2">
                {[["Ausbildung / Weiterbildung", candidate.ausbildung_titel], ["Aktuelles Umfeld", [candidate.aktuelles_umfeld_kanzleityp, candidate.aktuelles_umfeld_kanzleigroesse].filter(Boolean).join(" · ")], ["Remote-/Teilzeit-Wünsche", candidate.remote_teilzeit_wuensche], ["Passender Kanzleityp", candidate.passender_kanzleityp]].map(([label, value]) => <div key={label}><p className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">{label}</p><p className="mt-1.5 text-sm">{value || "—"}</p></div>)}
                {/* Nur bei rechtsanwalt relevant, siehe models/candidate.py::
                 * examensnoten - wird nur angezeigt, wenn tatsaechlich gesetzt. */}
                {candidate.examensnoten && (
                  <div><p className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">Examensnote</p><p className="mt-1.5 text-sm">{candidate.examensnoten}</p></div>
                )}
              </div>
              {/* Nur bei rechtsanwalt/rechtsfachangestellte inhaltlich
               * relevant, siehe models/candidate.py::rechtsgebiete. */}
              {candidate.rechtsgebiete && candidate.rechtsgebiete.length > 0 && (
                <div className="mt-6 border-t border-white/10 pt-5">
                  <p className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">Rechtsgebiete</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {candidate.rechtsgebiete.map((rechtsgebiet) => (
                      <span key={rechtsgebiet} className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-brand-platinum">{rechtsgebietLabel(rechtsgebiet)}</span>
                    ))}
                  </div>
                </div>
              )}
              {candidate.fachliche_schwerpunkte && candidate.fachliche_schwerpunkte.length > 0 && (
                <div className="mt-6 border-t border-white/10 pt-5">
                  <p className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">Fachliche Schwerpunkte</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {candidate.fachliche_schwerpunkte.map((item) => <span key={item} className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-brand-platinum">{item}</span>)}
                  </div>
                </div>
              )}
              {candidate.edv_kenntnisse && candidate.edv_kenntnisse.length > 0 && (
                <div className="mt-6 border-t border-white/10 pt-5">
                  <p className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">EDV-Kenntnisse</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {candidate.edv_kenntnisse.map((item) => <span key={item} className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-brand-platinum">{item}</span>)}
                  </div>
                </div>
              )}
              {candidate.berufliche_stationen && candidate.berufliche_stationen.length > 0 && (
                <div className="mt-6 border-t border-white/10 pt-5">
                  <p className="mb-2 text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">Berufliche Stationen</p>
                  <div className="space-y-1.5">
                    {candidate.berufliche_stationen.map((station, index) => (
                      <p key={index} className="text-sm text-brand-soft">{station.kanzleityp} · {station.kanzleigroesse} · {station.dauer_jahre} Jahre</p>
                    ))}
                  </div>
                </div>
              )}
              {candidate.freitext_notizen && (
                <div className="mt-6 border-t border-white/10 pt-5">
                  <p className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">Freitextnotizen</p>
                  <p className="mt-1.5 text-sm text-brand-soft">{candidate.freitext_notizen}</p>
                </div>
              )}
              {(candidate.wechselgrund || (candidate.no_gos && candidate.no_gos.length > 0)) && (
                <div className="mt-6 rounded-lg border border-brand-warning/25 bg-brand-warning/5 p-4">
                  <p className="mb-3 text-[9.5px] font-semibold uppercase tracking-wider text-brand-warning">Nur intern — nie in ausgehende Dokumente</p>
                  {candidate.wechselgrund && <div className="mb-3"><p className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">Wechselgrund</p><p className="mt-1.5 text-sm text-brand-soft">{candidate.wechselgrund}</p></div>}
                  {candidate.no_gos && candidate.no_gos.length > 0 && (
                    <div>
                      <p className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">No-Gos</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {candidate.no_gos.map((item) => <span key={item} className="rounded-full border border-brand-warning/25 bg-brand-warning/10 px-2.5 py-1 text-xs text-brand-warning">{item}</span>)}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent></Card>
            <Card><CardContent><h2 className="font-semibold">Nächster Schritt</h2><div className="mt-4 rounded-lg bg-brand-accent-soft/60 p-4 text-sm text-brand-platinum">{candidate.next_step ?? "Kontakt aufnehmen"}</div><div className="mt-5 flex items-center gap-2 text-xs text-[#747a80]"><MapPin size={14} />{candidate.city ?? "Keine Region"} · {candidate.postal_code ?? "keine PLZ"}</div></CardContent></Card>
          </div>
        </TabsContent>
        <TabsContent value="Anonymes Profil">
          <AnonymousProfilePanel
            candidateId={candidate.id}
            initialText={anonymousProfile}
            rollenUnbestaetigt={candidate.rollen_unbestaetigt}
          />
        </TabsContent>
        <TabsContent value="Notizen">
          <NotesPanel candidateId={candidate.id} initialNotes={notes} />
        </TabsContent>
        <TabsContent value="Matching">
          <CandidateMatchingPanel candidateId={candidate.id} />
        </TabsContent>
        <TabsContent value="CV-Outs">
          <div className="space-y-3">
            {submissions.map((item) => <Card key={item.id}><CardContent className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center"><div><p className="font-semibold">{clientName(item.client_company_id)}</p><p className="mt-1 text-xs text-brand-dim">Vorgestellt {formatDate(item.submitted_at)} · {item.next_step ?? "Nächster Schritt offen"}</p></div><div className="flex items-center gap-3"><StatusPill status={item.status} /><span className="text-xs text-brand-platinum">{item.expected_fee ? `${Number(item.expected_fee).toLocaleString("de-DE")} €` : ""}</span></div></CardContent></Card>)}
            {submissions.length === 0 && <Card><CardContent className="py-12 text-center text-sm text-brand-gray">Noch keine CV-Outs.</CardContent></Card>}
          </div>
        </TabsContent>
        <TabsContent value="Timeline">
          {/* EINE chronologische Liste aller Ereignisse (Statuswechsel/Aenderungen,
           * Aktivitaeten, Notizen, Feedback) mit Zeitpunkt und Urheber - siehe
           * candidate-timeline.tsx. */}
          <CandidateTimeline history={history} activities={activities} comments={comments} users={users} />
        </TabsContent>
        <TabsContent value="Aufgaben">
          <div className="space-y-2">
            {tasks.map((task) => (
              <Card key={task.id}>
                <CardContent className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                  <div>
                    <p className="font-semibold">{task.title}</p>
                    {task.description && <p className="mt-1 text-xs text-brand-muted">{task.description}</p>}
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusPill status={task.priority} />
                    <StatusPill status={task.status} />
                    <span className="text-xs text-brand-gray">{task.due_at ? formatDate(task.due_at) : "kein Termin"}</span>
                  </div>
                </CardContent>
              </Card>
            ))}
            {tasks.length === 0 && <Card><CardContent className="py-12 text-center text-sm text-brand-gray">Keine offenen Aufgaben für diesen Kandidaten.</CardContent></Card>}
          </div>
        </TabsContent>
        <TabsContent value="Dokumente">
          <DocumentPanel ownerType="candidate" ownerId={candidate.id} documentType="cv" documents={documents} />
        </TabsContent>
        {/* NOMICON: Arbeitnehmerüberlassung */}
        <TabsContent value="Überlassung">
          <StaffingCandidatePanel candidateId={candidate.id} />
        </TabsContent>
      </Tabs>
    </>
  );
}
