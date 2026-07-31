import { DemoNotice } from "@/components/crm/demo-notice";
import { ExportActions } from "@/components/crm/export-actions";
import { GeoResultsTable } from "@/components/crm/geo-results-table";
import { PageHeader } from "@/components/crm/page-header";
import { getGeoMappingResults } from "@/lib/api/queries";

export const dynamic = "force-dynamic";

export default async function GeoMappingPage() {
  const result = await getGeoMappingResults();
  const rows = result.data.map((item) => ({ Typ: item.kind, Name: item.name, Standort: item.location, PLZ: item.postal_code, Status: item.status, Mailing: item.mailing_ready ? "Ja" : "Nein" }));

  return (
    <>
      <PageHeader
        eyebrow="Standortbasierte Auswahl"
        title="Geo Mapping"
        action={<ExportActions filename="geo-mapping-ergebnisse" rows={rows} />}
      />
      <DemoNotice source={result.source} />
      {/* Karte und Tabelle teilen sich denselben Filterzustand (Ort/PLZ,
       * Umkreissuche, Rolle/Qualifikation/... - siehe GeoResultsTable) - die
       * Karte lebt deshalb in GeoResultsTable selbst statt hier als
       * getrennte Komponente mit dem ungefilterten result.data, sonst zeigt
       * sie weiterhin ausnahmslos alle Datensaetze an, waehrend die Tabelle
       * darunter schon gefiltert ist ("beim Eintippen wird trotzdem alles
       * angezeigt"-Bug). */}
      <GeoResultsTable results={result.data} />
    </>
  );
}
