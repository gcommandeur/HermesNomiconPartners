import { PageHeader } from "./page-header";
import { Card, CardContent } from "@/components/ui/card";
import { brand } from "@/lib/brand";

export function EmptyPage({ title }: { title: string; description?: string }) {
  return (
    <>
      <PageHeader eyebrow={brand.appName} title={title} />
      <Card><CardContent className="py-16 text-center text-sm text-brand-dim">Dieser Bereich ist im Grundgerüst vorbereitet und wird im nächsten fachlichen Schritt angebunden.</CardContent></Card>
    </>
  );
}
