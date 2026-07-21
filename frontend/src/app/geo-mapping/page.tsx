import { SlidersHorizontal } from "lucide-react";
import { DemoNotice } from "@/components/crm/demo-notice";
import { ExportActions } from "@/components/crm/export-actions";
import { GeoMapLoader } from "@/components/crm/geo-map-loader";
import { GeoResultsTable } from "@/components/crm/geo-results-table";
import { PageHeader } from "@/components/crm/page-header";
import { Card, CardContent } from "@/components/ui/card";
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
      <section className="mb-5 grid grid-cols-1 gap-5 xl:grid-cols-[1.1fr_.9fr]">
        <Card className="min-h-[360px] overflow-hidden p-0">
          <GeoMapLoader results={result.data} />
        </Card>
        <Card>
          <CardContent>
            <div className="flex items-center gap-2"><SlidersHorizontal size={16} className="text-[#D8DADF]" /><h2 className="font-semibold">Filterlogik</h2></div>
            <div className="mt-4 grid gap-2 text-xs text-[#CBD5E1]">
              {["Kandidaten: Rolle, Qualifikation, Umkreis, Gehalt, Kündigungsfrist, Verfügbarkeit, Arbeitsmodell", "Kanzleien: Status grün/grau/rot, Vertrag/AGB, Honorar, Ansprechpartner, aktive Vakanzen", "Do-not-touch wird für Mailing ausgeschlossen", "Auswahl per Checkbox unten in der Tabelle treffen und ins Mailing übernehmen"].map((item) => <div key={item} className="rounded-lg border border-white/10 bg-[#0D1B2E]/75 p-3">{item}</div>)}
            </div>
          </CardContent>
        </Card>
      </section>
      <GeoResultsTable results={result.data} />
    </>
  );
}
