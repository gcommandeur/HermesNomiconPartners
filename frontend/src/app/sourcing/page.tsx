import { PageHeader } from "@/components/crm/page-header";
import { SourcingLeadsTable } from "@/components/crm/sourcing-leads-table";
import { SourcingRunForm } from "@/components/crm/sourcing-run-form";

// Review-Seite des Sourcing-Agents: automatisiert gefundene Personen aus
// oeffentlichen Berufsregistern/Kanzlei-Team-Seiten landen hier als Lead-
// Vorschlaege und werden erst nach explizitem "Uebernehmen" zu echten
// Kandidaten (siehe Backend services/sourcing.py).
export default function SourcingPage() {
  return (
    <>
      <PageHeader
        eyebrow="Talent Sourcing"
        title="Sourcing"
        description="Automatisiert gefundene Kandidaten-Vorschläge – erst nach Bestätigung werden daraus echte Kandidaten."
      />
      <SourcingRunForm />
      <SourcingLeadsTable />
    </>
  );
}
