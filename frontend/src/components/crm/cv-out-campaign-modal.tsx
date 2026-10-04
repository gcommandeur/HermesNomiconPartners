"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { MapPinned, Search, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { ErrorBanner } from "@/components/crm/error-banner";
import { apiPost } from "@/lib/api/client";
import { getCvOutTargets } from "@/lib/api/queries";
import type { CvOutTargetClient, MailingGroup, MailingRecipient } from "@/lib/api/types";

const DEFAULT_RADIUS_KM = 50;
// Bestehende Vorlage "CV-Blindversand an Kanzlei" (siehe email_templates) -
// passt inhaltlich exakt zur CV-Out-Kampagne (anonymes Kurzprofil per
// Kandidat-Nr. an mehrere Kanzleien-Kontakte), daher keine neue Vorlage
// angelegt (Auftrag: "bestehende Vorlage pruefen, sonst neue anlegen").
const CV_OUT_TEMPLATE_KEY = "cv_blind_submission";

function dedupeKey(item: MailingRecipient): string {
  return item.email ? `email:${item.email.toLowerCase()}` : `${item.kind}:${item.id}`;
}

/** "CV Out"-Kampagne am Kandidaten (Auftrag '"CV Out"-Kampagne am
 * Kandidaten') - NICHT zu verwechseln mit dem bestehenden CV-Out-Status im
 * Matching-Tab (candidate-matching-panel.tsx): jenes ist eine reine
 * Pipeline-Statusmarkierung (legt eine CandidateSubmission an, kein
 * Mailversand), diese Kampagne hier verschickt tatsaechlich eine Mail an
 * mehrere Kanzlei-Kontakte im Umkreis. Radius um den Wohnort des Kandidaten
 * ist die einzige Eingabe (kein freier Ort-Text, siehe GET .../cv-out-targets
 * - Zentrum kommt serverseitig aus candidate.city/postal_code), Kanzleien mit
 * Status "Gesperrt" und Kontakte ohne E-Mail sind bereits serverseitig
 * ausgefiltert. Legt bei Bestaetigung eine MailingGroup (kind: "contact")
 * an und leitet dann in die bestehende Vorschau/Versand-Ansicht auf der
 * Mailing-Seite ueber (siehe mailing-groups-panel.tsx). */
export function CvOutCampaignModal({
  candidateId,
  candidateName,
  onClose,
}: {
  candidateId: string;
  candidateName: string;
  onClose: () => void;
}) {
  const router = useRouter();
  const [radiusKm, setRadiusKm] = useState(DEFAULT_RADIUS_KM);
  const [targets, setTargets] = useState<CvOutTargetClient[] | null>(null);
  const [selectedContactIds, setSelectedContactIds] = useState<Set<string>>(new Set());
  const [searching, setSearching] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch() {
    setSearching(true);
    setError(null);
    try {
      const result = await getCvOutTargets(candidateId, radiusKm);
      if (result.source === "demo") {
        setError("Demo-Modus: keine echte Umkreissuche verfügbar.");
        setTargets([]);
        return;
      }
      setTargets(result.data.targets);
      // Alle mailingfaehigen Kontakte sind vorausgewaehlt (Auftrag: "Liste
      // mit vorausgewaehlten Kontaktpersonen") - der Nutzer kann einzelne
      // vor dem Anlegen der Gruppe wieder abwaehlen.
      setSelectedContactIds(
        new Set(result.data.targets.flatMap((client) => client.contacts.map((c) => c.id))),
      );
    } catch (exception) {
      const message = exception instanceof Error ? exception.message : "Umkreissuche fehlgeschlagen.";
      // ConsentNotGrantedError (backend/src/cc_crm/core/errors.py) liefert
      // immer den Text "Kein Einverständnis ..." - Erkennung ueber diese
      // Teilzeichenkette statt eines eigenen Fehlercodes, da apiGet/getCvOutTargets
      // (siehe lib/api/queries.ts) nur die Fehlermeldung durchreicht, nicht den
      // HTTP-Status (gleiches Musters wie die bestehenden Backend-Tests, die
      // ebenfalls per Teilstring auf "Einverständnis" pruefen statt auf 403).
      setError(
        message.includes("Einverständnis")
          ? `Für ${candidateName} liegt noch keine Einwilligung zur Weitergabe vor. Bitte im Kandidaten-Profil unter „Bearbeiten“ die Einwilligung erfassen.`
          : message,
      );
    } finally {
      setSearching(false);
    }
  }

  function toggleContact(contactId: string) {
    setSelectedContactIds((current) => {
      const next = new Set(current);
      if (next.has(contactId)) next.delete(contactId);
      else next.add(contactId);
      return next;
    });
  }

  function toggleClient(client: CvOutTargetClient) {
    const allSelected = client.contacts.every((c) => selectedContactIds.has(c.id));
    setSelectedContactIds((current) => {
      const next = new Set(current);
      for (const contact of client.contacts) {
        if (allSelected) next.delete(contact.id);
        else next.add(contact.id);
      }
      return next;
    });
  }

  async function handleCreateAndSend() {
    if (!targets || selectedContactIds.size === 0) return;
    setCreating(true);
    setError(null);
    try {
      const recipients: MailingRecipient[] = [];
      const seen = new Set<string>();
      for (const client of targets) {
        for (const contact of client.contacts) {
          if (!selectedContactIds.has(contact.id)) continue;
          const recipient: MailingRecipient = {
            kind: "contact",
            id: contact.id,
            name: `${contact.first_name} ${contact.last_name}`.trim() || client.name,
            email: contact.email,
          };
          const key = dedupeKey(recipient);
          if (seen.has(key)) continue;
          seen.add(key);
          recipients.push(recipient);
        }
      }
      const groupName = `CV-Out ${candidateName} · ${radiusKm}km · ${new Date().toLocaleDateString("de-DE")}`;
      const group = await apiPost<MailingGroup>("/mailing-groups", {
        name: groupName,
        recipients,
        template_key: CV_OUT_TEMPLATE_KEY,
      });
      router.push(`/mailing?group=${group.id}`);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Mailing-Gruppe konnte nicht angelegt werden.");
      setCreating(false);
    }
  }

  const selectedCount = selectedContactIds.size;

  return (
    <Modal
      title="CV-Out-Kampagne"
      eyebrow={candidateName}
      description="Kanzleien im Umkreis des Wohnorts, außer Status „Gesperrt“ - versendet das anonyme Kurzprofil an die ausgewählten Kanzlei-Kontakte."
      maxWidth="max-w-2xl"
      onClose={onClose}
    >
      <div className="space-y-4">
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className="mb-1 block text-xs text-brand-muted">Radius (km)</label>
            <Input
              type="number"
              min={1}
              max={500}
              value={radiusKm}
              onChange={(e) => setRadiusKm(Math.max(1, Math.min(500, Number(e.target.value) || 1)))}
            />
          </div>
          <Button disabled={searching} onClick={handleSearch}>
            <Search size={14} />
            {searching ? "Suche…" : "Kanzleien suchen"}
          </Button>
        </div>

        <ErrorBanner message={error} />

        {targets !== null && (
          <>
            <p className="flex items-center gap-1.5 text-xs text-brand-muted">
              <MapPinned size={13} />
              {targets.length} Kanzlei(en) im Umkreis von {radiusKm} km mit mailingfähigem Kontakt · {selectedCount} Kontakt(e) ausgewählt
            </p>
            <div className="max-h-80 space-y-2 overflow-y-auto">
              {targets.map((client) => {
                const allSelected = client.contacts.every((c) => selectedContactIds.has(c.id));
                return (
                  <Card key={client.id}>
                    <CardContent className="space-y-2">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-start gap-2">
                          <input
                            type="checkbox"
                            className="mt-1 size-4 shrink-0 accent-brand-accent"
                            checked={allSelected}
                            onChange={() => toggleClient(client)}
                            aria-label={`Alle Kontakte von ${client.name} auswählen`}
                          />
                          <div>
                            <p className="font-semibold">{client.name}</p>
                            <p className="mt-0.5 text-xs text-brand-muted">{client.location}</p>
                          </div>
                        </div>
                        <span className="shrink-0 rounded-full bg-brand-accent-soft px-2.5 py-1 text-[9.5px] text-brand-platinum">
                          {client.distance_km} km
                        </span>
                      </div>
                      <div className="ml-6 space-y-1 border-t border-white/10 pt-2">
                        {client.contacts.map((contact) => (
                          <label key={contact.id} className="flex items-center gap-2 text-xs text-brand-soft">
                            <input
                              type="checkbox"
                              checked={selectedContactIds.has(contact.id)}
                              onChange={() => toggleContact(contact.id)}
                            />
                            {contact.first_name} {contact.last_name}
                            {contact.role_title ? ` · ${contact.role_title}` : ""}
                            {contact.is_primary ? " · Hauptkontakt" : ""}
                            <span className="text-brand-gray">({contact.email})</span>
                          </label>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
              {targets.length === 0 && (
                <Card><CardContent className="py-8 text-center text-sm text-brand-gray">
                  Keine passenden Kanzleien im Umkreis gefunden.
                </CardContent></Card>
              )}
            </div>
          </>
        )}

        <div className="flex justify-end gap-2 border-t border-white/10 pt-4">
          <Button variant="outline" onClick={onClose}>Abbrechen</Button>
          <Button disabled={!targets || selectedCount === 0 || creating} onClick={handleCreateAndSend}>
            <Send size={14} />
            {creating ? "Lege an…" : `Mailing-Gruppe anlegen (${selectedCount})`}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export function CvOutCampaignButton({
  candidateId,
  candidateName,
}: {
  candidateId: string;
  candidateName: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <MapPinned size={13} />
        CV-Out-Kampagne
      </Button>
      {open && (
        <CvOutCampaignModal
          candidateId={candidateId}
          candidateName={candidateName}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
