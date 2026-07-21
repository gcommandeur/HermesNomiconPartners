import { DemoNotice } from "@/components/crm/demo-notice";
import { ExportActions } from "@/components/crm/export-actions";
import { GeoMapLoader } from "@/components/crm/geo-map-loader";
import { GeoResultsTable } from "@/components/crm/geo-results-table";
import { PageHeader } from "@/components/crm/page-header";
import { Card } from "@/components/ui/card";
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
      {/* Die frueher hier stehende "Filterlogik"-Karte war reiner
       * Fliesstext ohne Funktion - die echten, funktionierenden Filter
       * (Rolle/Qualifikation/Kuendigungsfrist/Verfuegbarkeit bei
       * Kandidaten, AGB-Status/Honorar-Stufe/aktive Vakanzen bei Kanzleien,
       * Umkreis-Suche per Zentrum+Radius) stehen jetzt direkt ueber der
       * Ergebnistabelle in GeoResultsTable. */}
      <Card className="mb-5 min-h-[360px] overflow-hidden p-0">
        <GeoMapLoader results={result.data} />
      </Card>
      <GeoResultsTable results={result.data} />
    </>
  );
}
