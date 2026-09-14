import { ShieldCheck } from "lucide-react";
import { DemoNotice } from "@/components/crm/demo-notice";
import { EmailTemplatesPanel } from "@/components/crm/email-templates-panel";
import { MailingGroupsPanel } from "@/components/crm/mailing-groups-panel";
import { PageHeader } from "@/components/crm/page-header";
import { getEmailTemplates } from "@/lib/api/queries";

export const dynamic = "force-dynamic";

// Empfaenger kommen nicht mehr aus einer hartcodierten "alle Hauptkontakte"-
// Regel, sondern aus gespeicherten Mailing-Gruppen (Punkt 6: Geo-Mapping-
// Auswahl / "Fuer Mailing nutzen" auf Kandidaten-/Kanzlei-/Kontaktprofilen).
// Vorlagen liegen seit "Mailvorlagen editierbar machen" in der DB und werden
// client-seitig per SWR gecached (siehe useEmailTemplatesCache) statt als
// statischer Prop durchgereicht - dieser Server-Fetch dient nur noch dazu,
// im Demo-Modus (kein Backend erreichbar) den DemoNotice-Banner zu zeigen.
export default async function MailingPage() {
  const templates = await getEmailTemplates();

  return (
    <>
      <PageHeader eyebrow="Outlook-Entwürfe und Kampagnen" title="Mailing" />
      <DemoNotice source={templates.source} error={templates.error} />
      <div className="mb-5 flex items-center gap-2 rounded-lg border border-white/10 bg-[#0D1B2E] p-3 text-xs text-[#CBD5E1]"><ShieldCheck size={15} />Nur Text-Vorschau und Kopieren - keine Outlook-Anbindung vorhanden, Versand folgt erst nach expliziter Freigabe und Einrichtung einer echten Integration.</div>
      <div className="space-y-8">
        <MailingGroupsPanel />
        <EmailTemplatesPanel />
      </div>
    </>
  );
}
