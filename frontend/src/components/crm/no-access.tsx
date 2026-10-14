// NOMICON: Ansichten - nur in der Nomicon-Kopie. Plain-Komponente (Server und Client nutzbar).
import Link from "next/link";
import { ShieldOff } from "lucide-react";
import { PageHeader } from "./page-header";
import { Card, CardContent } from "@/components/ui/card";
import { brand } from "@/lib/brand";

export function NoAccess({ viewLabel }: { viewLabel?: string }) {
  return (
    <>
      <PageHeader eyebrow={brand.appName} title="Keine Freigabe" />
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
          <ShieldOff size={28} className="text-brand-muted" />
          <p className="text-sm font-semibold text-brand-text">
            {viewLabel ? `Die Ansicht „${viewLabel}“ ist nicht freigeschaltet` : "Diese Ansicht ist nicht freigeschaltet"}
          </p>
          <p className="max-w-sm text-xs text-brand-muted">
            Diese Ansicht ist für dein Konto nicht freigeschaltet. Wende dich an einen Admin, falls du
            sie brauchst.
          </p>
          <Link href="/" className="text-xs text-brand-accent-light underline">Zur Übersicht</Link>
        </CardContent>
      </Card>
    </>
  );
}
