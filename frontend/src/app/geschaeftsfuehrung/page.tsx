"use client";

import { useState } from "react";
import { ShieldOff } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorState } from "@/components/crm/error-state";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useCurrentUser, useTeamKpisCache } from "@/lib/api/hooks";
import { PITCH_LABEL, STAGE_LABELS } from "@/lib/stage-labels";

const STAGE_COLUMNS: { key: string; label: string }[] = [
  { key: "pitch", label: PITCH_LABEL },
  { key: "qualification_call", label: STAGE_LABELS.qualification_call },
  { key: "cv_in", label: STAGE_LABELS.cv_in },
  { key: "cv_out", label: STAGE_LABELS.cv_out },
  { key: "interview", label: STAGE_LABELS.interview },
  { key: "offer", label: STAGE_LABELS.offer },
  { key: "placement", label: STAGE_LABELS.placement },
];

const PERIOD_OPTIONS: { value: "week" | "month" | "quarter"; label: string }[] = [
  { value: "week", label: "Woche" },
  { value: "month", label: "Monat" },
  { value: "quarter", label: "Quartal" },
];

export default function GeschaeftsfuehrungPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const [period, setPeriod] = useState<"week" | "month" | "quarter">("week");
  const { data, isLoading, error, mutate: retry } = useTeamKpisCache(period, isAdmin);
  const members = data?.data.members ?? [];

  if (meLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-14 animate-pulse rounded-lg bg-[#0D1B2E]" />
        ))}
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow="Hermes" title="Geschäftsführung" />
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ShieldOff size={28} className="text-[#94A3B8]" />
            <p className="text-sm font-semibold text-[#F8FAFC]">Nur für Admins zugänglich</p>
            <p className="max-w-sm text-xs text-[#94A3B8]">
              Diese Übersicht zeigt die KPI-Werte aller Mitarbeiter:innen. Wende dich an einen
              Admin, falls du Zugriff benötigst.
            </p>
          </CardContent>
        </Card>
      </>
    );
  }

  if (error) {
    return <ErrorState onRetry={() => void retry()} />;
  }

  return (
    <>
      <PageHeader
        eyebrow="Hermes"
        title="Geschäftsführung"
        action={
          <div className="flex gap-1.5">
            {PERIOD_OPTIONS.map((option) => (
              <Button
                key={option.value}
                size="sm"
                variant={period === option.value ? "default" : "outline"}
                onClick={() => setPeriod(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
        }
      />

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-14 animate-pulse rounded-lg bg-[#0D1B2E]" />
          ))}
        </div>
      ) : members.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-xs text-[#94A3B8]">
            Keine aktiven Mitarbeiter:innen gefunden.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-white/10 text-[10px] uppercase tracking-wider text-[#94A3B8]">
                  <th className="px-4 py-3">Mitarbeiter:in</th>
                  {STAGE_COLUMNS.map((column) => (
                    <th key={column.key} className="px-3 py-3 text-right">{column.label}</th>
                  ))}
                  <th className="px-3 py-3 text-right">Punkte</th>
                  <th className="px-3 py-3 text-right">Ziel</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.user_id} className="border-b border-white/5">
                    <td className="px-4 py-3 font-semibold text-[#F8FAFC]">{member.display_name}</td>
                    {STAGE_COLUMNS.map((column) => (
                      <td key={column.key} className="px-3 py-3 text-right text-[#D8DADF]">
                        {member.stages[column.key] ?? 0}
                      </td>
                    ))}
                    <td className="px-3 py-3 text-right text-sm font-bold text-[#69A7EA]">
                      {member.points}
                    </td>
                    {/* Ziel-Spalte bewusst vorbereitet, aber leer - Soll-Werte
                     * pro Mitarbeiter sind noch nicht definiert (Nutzer-
                     * Vorgabe: nicht raten), Backend liefert dafuer immer
                     * `target: null`. */}
                    <td className="px-3 py-3 text-right text-[#5b6167]">–</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </>
  );
}
