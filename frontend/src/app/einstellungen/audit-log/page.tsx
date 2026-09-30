"use client";

import { ShieldOff } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorState } from "@/components/crm/error-state";
import { Card, CardContent } from "@/components/ui/card";
import { useAuditLogsCache, useCurrentUser } from "@/lib/api/hooks";
import { formatDateTime } from "@/lib/utils";

const ACTION_LABELS: Record<string, string> = {
  admin_fields_changed: "Admin-Recht/Status geändert",
  deleted: "Gelöscht",
  updated: "Bearbeitet",
  password_reset: "Passwort zurückgesetzt",
  calendar_feed_token_rotated: "Kalender-Feed-Token neu generiert",
};

const ENTITY_LABELS: Record<string, string> = {
  user: "Nutzer",
  candidate: "Kandidat",
  client_company: "Kanzlei",
  candidate_submission: "Prozess",
};

function describeValues(values: Record<string, unknown> | null): string | null {
  if (!values) return null;
  const parts = Object.entries(values).map(([key, value]) => `${key}: ${String(value)}`);
  return parts.length > 0 ? parts.join(", ") : null;
}

export default function AuditLogPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const { data, isLoading, error, mutate: retry } = useAuditLogsCache(isAdmin);
  const entries = data?.data ?? [];

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
        <PageHeader eyebrow="Hermes" title="Audit-Log" />
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ShieldOff size={28} className="text-[#94A3B8]" />
            <p className="text-sm font-semibold text-[#F8FAFC]">Nur für Admins zugänglich</p>
            <p className="max-w-sm text-xs text-[#94A3B8]">
              Dieser Bereich ist der Nachvollziehbarkeit sicherheits-/administrativ relevanter
              Aktionen vorbehalten. Wende dich an einen Admin, falls du Zugriff benötigst.
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
      <PageHeader eyebrow="Hermes" title="Audit-Log" />
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="h-14 animate-pulse rounded-lg bg-[#0D1B2E]" />
          ))}
        </div>
      ) : entries.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-xs text-[#94A3B8]">
            Noch keine Einträge.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="rounded-lg border border-white/10 bg-[#0D1B2E]/85 p-3 text-xs"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-[#F8FAFC]">
                  {ACTION_LABELS[entry.action] ?? entry.action}
                  <span className="ml-2 font-normal text-[#94A3B8]">
                    {ENTITY_LABELS[entry.entity_type] ?? entry.entity_type}
                  </span>
                </span>
                <span className="text-[#94A3B8]">{formatDateTime(entry.changed_at)}</span>
              </div>
              <p className="mt-1 text-[#CBD5E1]">
                Von: {entry.changed_by ?? "unbekannt"}
              </p>
              {(describeValues(entry.old_values) || describeValues(entry.new_values)) && (
                <p className="mt-1 text-[11px] text-[#747C89]">
                  {describeValues(entry.old_values) && `vorher: ${describeValues(entry.old_values)}`}
                  {describeValues(entry.old_values) && describeValues(entry.new_values) && " · "}
                  {describeValues(entry.new_values) && `nachher: ${describeValues(entry.new_values)}`}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
