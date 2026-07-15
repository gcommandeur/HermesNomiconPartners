import { Badge } from "@/components/ui/badge";

const labels: Record<string, string> = {
  active: "Aktiv", passive: "Passiv", placed: "Platziert", blocked: "Gesperrt", archived: "Archiviert",
  acquisition: "In Verhandlung", prospect: "Noch kein Kontakt",
  qualification_call: "Quali Call", cv_in: "CV IN", cv_out: "CV OUT", interview: "Interview",
  offer: "Offer", placement: "Placement", cancelled: "Abgebrochen",
  candidate_rejected: "Absage Kandidat", client_rejected: "Absage Kanzlei",
  candidate_ghosting: "Ghosting Kandidat",
  open: "Offen", on_hold: "Pausiert", filled: "Besetzt", closed: "Geschlossen", draft: "Entwurf",
  low: "Niedrig", normal: "Normal", high: "Hoch", urgent: "Dringend",
};

function tone(status: string) {
  if (["active", "placed", "filled", "placement"].includes(status)) return "green" as const;
  if (["blocked", "cancelled"].includes(status)) return "red" as const;
  if (["acquisition", "on_hold", "offer"].includes(status)) return "amber" as const;
  if (["cv_out", "interview", "qualification_call"].includes(status)) return "blue" as const;
  return "gray" as const;
}

export function StatusPill({ status }: { status: string }) {
  return <Badge tone={tone(status)}>{labels[status] ?? status}</Badge>;
}
