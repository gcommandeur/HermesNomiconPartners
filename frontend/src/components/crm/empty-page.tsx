import { PageHeader } from "./page-header";
import { Card, CardContent } from "@/components/ui/card";

export function EmptyPage({ title }: { title: string; description?: string }) {
  return (
    <>
      <PageHeader eyebrow="Hermes" title={title} />
      <Card><CardContent className="py-16 text-center text-sm text-[#777d83]">Dieser Bereich ist im Grundgerüst vorbereitet und wird im nächsten fachlichen Schritt angebunden.</CardContent></Card>
    </>
  );
}
