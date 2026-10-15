import { DemoNotice } from "@/components/crm/demo-notice";
import { EmailTemplatesPanel } from "@/components/crm/email-templates-panel";
import { MailingGroupsPanel } from "@/components/crm/mailing-groups-panel";
import { PageHeader } from "@/components/crm/page-header";
import { getEmailTemplates } from "@/lib/api/queries";

export const dynamic = "force-dynamic";

// Empfaenger kommen nicht mehr aus einer hartcodierten "alle Hauptkontakte"-
// Regel, sondern aus gespeicherten Mailing-Gruppen (Punkt 6: Geo-Mapping-
// Auswahl / "Fuer Mailing nutzen" auf Kandidaten-/Kunden-/Kontaktprofilen).
// Vorlagen liegen seit "Mailvorlagen editierbar machen" in der DB und werden
// client-seitig per SWR gecached (siehe useEmailTemplatesCache) statt als
// statischer Prop durchgereicht - dieser Server-Fetch dient nur noch dazu,
// im Demo-Modus (kein Backend erreichbar) den DemoNotice-Banner zu zeigen.
export default async function MailingPage({
  searchParams,
}: {
  searchParams?: Promise<{ group?: string }>;
}) {
  const templates = await getEmailTemplates();
  const { group } = (await searchParams) ?? {};

  return (
    <>
      <PageHeader eyebrow="Outlook-Entwürfe und Kampagnen" title="Mailing" />
      <DemoNotice source={templates.source} error={templates.error} />
      <div className="space-y-8">
        <MailingGroupsPanel initialPreviewGroupId={group ?? null} />
        <EmailTemplatesPanel />
      </div>
    </>
  );
}
