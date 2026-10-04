import Link from "next/link";
import { ArrowLeft, Building2, Mail, Phone, Star } from "lucide-react";
import { getCandidates, getClients, getContacts, getDocumentsForOwner, getGroupLocations, getSubmissions } from "@/lib/api/queries";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StatusPill } from "@/components/crm/status-pill";
import { ClientHonorarEditor } from "@/components/crm/client-honorar-editor";
import { DocumentPanel } from "@/components/crm/document-panel";
import { CustomFieldsPanel } from "@/components/crm/custom-fields-panel";
import { ClientEditModal } from "@/components/crm/client-create-modal";
import { ApprovalPendingNotice } from "@/components/crm/approval-pending-notice";
import { AddToMailingButton } from "@/components/crm/add-to-mailing-button";
import { MailComposeButton } from "@/components/crm/mail-compose-modal";
import { contactName, formatCurrency, formatDate, termsStatusLabel } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function ClientDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [clients, submissions, candidates, contacts] = await Promise.all([getClients(), getSubmissions(), getCandidates(), getContacts()]);
  const client = clients.data.find((item) => item.id === id) ?? clients.data[0];
  const documents = (await getDocumentsForOwner("client", client.id)).data;
  const groupLocations = (await getGroupLocations(client.id)).data;
  const clientSubmissions = submissions.data.filter((item) => item.client_company_id === client.id);
  const clientContacts = contacts.data.filter((contact) => contact.client_company_id === client.id);
  const primaryContact = clientContacts.find((contact) => contact.is_primary);
  const candidateName = (candidateId: string) => {
    const item = candidates.data.find((candidate) => candidate.id === candidateId);
    return item ? `${item.first_name} ${item.last_name}` : "Kandidat";
  };
  const expectedFees = clientSubmissions.reduce((sum, item) => sum + Number(item.expected_fee ?? 0), 0);

  return (
    <>
      <Link href="/kanzleien" className="mb-5 inline-flex items-center gap-2 text-xs text-brand-muted hover:text-brand-platinum"><ArrowLeft size={14} />Zur Kanzleiliste</Link>
      <div className="mb-6 flex flex-col justify-between gap-4 border-b border-white/10 pb-6 sm:flex-row sm:items-end">
        <div>
          <div className="mb-3 flex items-center gap-2">
            <StatusPill status={client.status} />
            {client.kanzleigruppe && <span className="rounded-full border border-brand-accent/30 bg-brand-accent/10 px-2 py-1 text-[10px] uppercase tracking-wider text-brand-muted">{client.kanzleigruppe}</span>}
          </div>
          <h1 className="text-3xl font-semibold tracking-[-.035em]">{client.name}</h1>
          <p className="mt-2 text-sm text-brand-soft">{client.focus ?? "Fokus offen"} · {client.region ?? client.city ?? "Region offen"}</p>
          <ApprovalPendingNotice entityType="client_company" entityId={client.id} />
        </div>
        <div className="flex flex-wrap items-center gap-4 text-xs text-brand-soft">
          {client.email && <span className="flex items-center gap-1.5"><Mail size={14} />{client.email}</span>}
          {client.phone && <span className="flex items-center gap-1.5"><Phone size={14} />{client.phone}</span>}
          {client.email && (
            <AddToMailingButton recipient={{ kind: "client", id: client.id, name: client.name, email: client.email }} />
          )}
          {client.email && (
            <MailComposeButton
              toAddress={client.email}
              toName={client.name}
              clientCompanyId={client.id}
              documentOwnerType="client"
              documentOwnerId={client.id}
              placeholderValues={{ client: client.name, contact: primaryContact ? contactName(primaryContact) : client.name }}
            />
          )}
          <ClientEditModal client={client} />
        </div>
      </div>
      <CustomFieldsPanel entityType="client" entityId={client.id} initialValues={client.custom_fields} />
      <Tabs defaultValue="Übersicht">
        <TabsList className="mb-5"><TabsTrigger value="Übersicht">Übersicht</TabsTrigger><TabsTrigger value="Kontakte">Kontakte</TabsTrigger><TabsTrigger value="Kandidaten">Vorgestellte Kandidaten</TabsTrigger><TabsTrigger value="Konditionen">Konditionen / AGB</TabsTrigger><TabsTrigger value="Dokumente">Dokumente</TabsTrigger></TabsList>
        <TabsContent value="Übersicht">
          <section className="grid grid-cols-1 gap-4 md:grid-cols-4">{[["Hauptkontakt", primaryContact ? contactName(primaryContact) : (client.contact_name ?? "Offen")], ["Aktive Prozesse", clientSubmissions.length], ["Aktive Mandate", client.active_mandates ?? 0], ["Erwartete Fees", formatCurrency(expectedFees)]].map(([label, value]) => <Card key={String(label)}><CardContent><p className="text-xs text-brand-dim">{label}</p><p className="mt-3 text-xl font-semibold">{value}</p></CardContent></Card>)}</section>
          {groupLocations.length > 0 && (
            <Card className="mt-4">
              <CardContent>
                <div className="flex items-center gap-2"><Building2 size={15} className="text-brand-platinum" /><h2 className="font-semibold">Weitere Standorte der Kanzleigruppe &quot;{client.kanzleigruppe}&quot;</h2></div>
                <div className="mt-4 space-y-2">
                  {groupLocations.map((location) => (
                    <Link key={location.id} href={`/kanzleien/${location.id}`} className="flex items-center justify-between rounded-lg border border-white/10 bg-brand-surface/75 p-3 text-sm hover:border-brand-accent/50">
                      <span className="font-medium">{location.name}</span>
                      <span className="text-xs text-brand-muted">{[location.street, location.postal_code, location.city].filter(Boolean).join(", ") || "Adresse offen"}</span>
                    </Link>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
        <TabsContent value="Kontakte"><div className="space-y-2">{clientContacts.map((contact) => <Card key={contact.id}><CardContent className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div><p className="font-semibold">{contactName(contact)}</p><p className="mt-1 text-xs text-brand-muted">{contact.role_title ?? "Rolle offen"} · {contact.email ?? "keine E-Mail"}</p></div><div className="flex items-center gap-3">{contact.is_primary && <span className="inline-flex items-center gap-1 rounded-full border border-brand-platinum/25 bg-brand-platinum/10 px-2 py-1 text-[10px] text-brand-text"><Star size={11} />Hauptkontakt</span>}{contact.phone && <span className="text-xs text-brand-muted">{contact.phone}</span>}{contact.email && <MailComposeButton toAddress={contact.email} toName={contactName(contact)} contactPersonId={contact.id} clientCompanyId={client.id} placeholderValues={{ contact: contactName(contact), client: client.name }} label="Mail" />}</div></CardContent></Card>)}{clientContacts.length === 0 && <Card><CardContent className="py-12 text-center text-sm text-brand-gray">Noch keine Kontakte.</CardContent></Card>}</div></TabsContent>
        <TabsContent value="Kandidaten"><div className="space-y-2">{clientSubmissions.map((item) => <Card key={item.id}><CardContent className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-semibold">{candidateName(item.candidate_id)}</p><p className="mt-1 text-xs text-brand-dim">Vorgestellt {formatDate(item.submitted_at)}</p></div><StatusPill status={item.status} /></CardContent></Card>)}</div></TabsContent>
        <TabsContent value="Konditionen">
          <div className="space-y-4">
            <ClientHonorarEditor client={client} />
            <Card><CardContent className="grid grid-cols-1 gap-5 md:grid-cols-2"><div><p className="text-xs text-brand-dim">AGB-Status</p><p className="mt-2 font-medium">{termsStatusLabel(client.terms_status)}</p></div><div><p className="text-xs text-brand-dim">Rückzahlung</p><p className="mt-2 text-sm">{client.refund_terms ?? "50 % vor Antritt; 50 % im ersten Monat; 25 % im zweiten Monat"}</p></div><div><p className="text-xs text-brand-dim">Zahlungsziel / Garantie</p><p className="mt-2 text-sm">{client.payment_terms_days ?? 14} Tage · {client.guarantee_period_months ?? 6} Monate</p></div></CardContent></Card>
          </div>
        </TabsContent>
        <TabsContent value="Dokumente">
          <DocumentPanel ownerType="client" ownerId={client.id} documentType="vertrag" documents={documents} />
        </TabsContent>
      </Tabs>
    </>
  );
}
