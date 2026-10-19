"use client";

// NOMICON: Überlassung - Compliance nur für Admins und Teamleiter (der Server antwortet für alle
// anderen mit 404; diese Sperre ist nur die freundliche Seite dazu).
import Link from "next/link";
import { ShieldOff } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { useCurrentUser } from "@/lib/api/hooks";
import { canSeeCompliance } from "@/lib/staffing-roles";
import { LoadingRows } from "./staffing-ui";

export function StaffingComplianceGate({ children }: { children: React.ReactNode }) {
  const { data } = useCurrentUser();
  if (!data) return <LoadingRows rows={2} />;
  if (canSeeCompliance(data.data)) return <>{children}</>;
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <ShieldOff size={28} className="text-brand-muted" />
        <p className="text-sm font-semibold">Compliance ist für Admins und Teamleiter</p>
        <p className="max-w-sm text-xs text-brand-muted">
          Fristen, Equal Pay, überfällige Einsätze und Erlaubnis meldet das System von selbst: als Aufgabe und in der Glocke oben rechts.
        </p>
        <Link href="/ueberlassung" className="text-xs text-brand-accent-light underline">Zur Übersicht</Link>
      </CardContent>
    </Card>
  );
}
