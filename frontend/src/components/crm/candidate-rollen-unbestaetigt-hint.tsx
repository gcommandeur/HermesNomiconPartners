"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Pencil, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CandidateEditModal } from "@/components/crm/candidate-create-modal";
import { confirmCandidateRollen } from "@/lib/api/queries";
import type { Candidate } from "@/lib/api/types";

/** Titelschutz-Korrektur Schritt 2 (Markieren statt Aendern): dezenter
 * Hinweis am Rollen-Badge, wenn candidate.rollen_unbestaetigt gesetzt ist
 * (geschuetzte Rolle steuerberater/wirtschaftspruefer/rechtsanwalt ohne
 * erkennbaren Beleg im CV, siehe Backend scripts/
 * audit_titelschutz_unverified_roles.py), plus die beiden Aktionen:
 * - "Bestätigen": Nutzer hat den Titel geprueft (z.B. im Original-CV
 *   nachgesehen) und bestaetigt ihn - loescht nur das Flag, rollen bleibt
 *   unangetastet.
 * - "Rolle korrigieren": oeffnet die normale Rollen-Bearbeitung
 *   (CandidateEditModal) - das Flag verschwindet automatisch, sobald rollen
 *   sich dadurch tatsaechlich aendert (siehe Backend
 *   CandidateService.update()).
 * Beide Aktionen schreiben serverseitig einen AuditLog-Eintrag (siehe
 * candidate-history-panel.tsx fuer die Anzeige). */
export function CandidateRollenUnbestaetigtHint({ candidate }: { candidate: Candidate }) {
  const router = useRouter();
  const [correcting, setCorrecting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!candidate.rollen_unbestaetigt) return null;

  async function handleConfirm() {
    setConfirming(true);
    setError(null);
    try {
      await confirmCandidateRollen(candidate.id);
      router.refresh();
    } catch (exception) {
      setError(
        exception instanceof Error ? exception.message : "Konnte nicht bestätigt werden.",
      );
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <Badge tone="amber" className="gap-1.5" title="Geschützte Rolle ohne erkennbaren Beleg im CV">
        <ShieldAlert size={12} />Titel unbestätigt
      </Badge>
      <Button size="sm" variant="outline" disabled={confirming} onClick={handleConfirm}>
        <Check size={13} />{confirming ? "Bestätigen…" : "Bestätigen"}
      </Button>
      <Button size="sm" variant="outline" onClick={() => setCorrecting(true)}>
        <Pencil size={13} />Rolle korrigieren
      </Button>
      {error && <span className="text-xs text-red-400">{error}</span>}
      <CandidateEditModal
        candidate={candidate}
        open={correcting}
        onOpenChange={setCorrecting}
        hideTrigger
        onUpdated={() => {
          setCorrecting(false);
          router.refresh();
        }}
      />
    </div>
  );
}
