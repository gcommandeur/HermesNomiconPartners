"use client";

import { useState } from "react";
import Link from "next/link";
import { ShieldOff } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorState } from "@/components/crm/error-state";
import { ErrorBanner } from "@/components/crm/error-banner";
import { DataTable } from "@/components/crm/data-table";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { assignSubmissionOwner } from "@/lib/api/queries";
import {
  invalidateUnownedSubmissionsCache,
  useAdminUsersCache,
  useCurrentUser,
  useUnownedSubmissionsCache,
} from "@/lib/api/hooks";
import { STAGE_LABELS } from "@/lib/stage-labels";
import { brand } from "@/lib/brand";

const selectClass =
  "h-9 rounded-md border border-white/15 bg-brand-surface px-2 text-sm text-brand-platinum focus:outline-none focus:ring-2 focus:ring-brand-accent/30 disabled:opacity-50";

/** Nur Admin: Prozesse ohne Verantwortlichen (Altdaten aus der Zeit vor dem Owner-Feld). Fuer
 * Nicht-Admins sind sie unsichtbar - hier sieht man sie und weist sie zu. */
export default function ProzesseOhneVerantwortlichenPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const { data, isLoading, error, mutate: retry } = useUnownedSubmissionsCache(isAdmin);
  const { data: usersData } = useAdminUsersCache(isAdmin);
  const users = (usersData?.data ?? []).filter((user) => user.is_active);
  const items = data?.data.items ?? [];
  const [choice, setChoice] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  async function assign(submissionId: string) {
    const ownerId = choice[submissionId];
    if (!ownerId) return;
    setBusyId(submissionId);
    setRowError(null);
    try {
      await assignSubmissionOwner(submissionId, ownerId);
      await Promise.all([retry(), invalidateUnownedSubmissionsCache()]);
    } catch (exception) {
      setRowError(exception instanceof Error ? exception.message : "Zuweisen fehlgeschlagen.");
    } finally {
      setBusyId(null);
    }
  }

  if (meLoading) {
    return <div className="h-14 animate-pulse rounded-lg bg-brand-surface" />;
  }
  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow={brand.appName} title="Prozesse ohne Verantwortlichen" />
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ShieldOff size={28} className="text-brand-muted" />
            <p className="text-sm font-semibold text-brand-text">Nur für Admins zugänglich</p>
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
      <PageHeader eyebrow={brand.appName} title="Prozesse ohne Verantwortlichen" />
      <p className="mb-4 max-w-2xl text-xs text-brand-muted">
        Diese Prozesse haben keinen Verantwortlichen (aus der Zeit vor dem Feld). Für Mitarbeiter und
        Teamleiter sind sie unsichtbar und tauchen in deren Listen und Kennzahlen nicht auf, bis du
        sie zuweist.
      </p>
      <ErrorBanner message={rowError} className="mb-3" />
      {isLoading ? (
        <div className="h-14 animate-pulse rounded-lg bg-brand-surface" />
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-xs text-brand-muted">
            Alle Prozesse haben einen Verantwortlichen.
          </CardContent>
        </Card>
      ) : (
        <DataTable headers={["Kandidat", "Kunde", "Status", "Angelegt", "Verantwortlicher"]}>
          {items.map((item) => (
            <tr key={item.id} className="hover:bg-brand-hover/25">
              <td className="px-4 py-3.5 font-medium text-brand-text">
                <Link href={`/kandidaten/${item.candidate_id}`} className="hover:underline">
                  {item.candidate_name}
                </Link>
              </td>
              <td className="px-4 py-3.5 text-brand-soft">{item.client_name ?? "—"}</td>
              <td className="px-4 py-3.5 text-brand-soft">
                {STAGE_LABELS[item.status as keyof typeof STAGE_LABELS] ?? item.status}
              </td>
              <td className="px-4 py-3.5 text-brand-soft">
                {new Date(item.created_at).toLocaleDateString("de-DE")}
              </td>
              <td className="px-4 py-3.5">
                <div className="flex items-center gap-2">
                  <select
                    className={selectClass}
                    value={choice[item.id] ?? ""}
                    disabled={busyId === item.id}
                    onChange={(event) => setChoice((current) => ({ ...current, [item.id]: event.target.value }))}
                    aria-label={`Verantwortlicher für ${item.candidate_name}`}
                  >
                    <option value="">Nutzer wählen…</option>
                    {users.map((user) => (
                      <option key={user.id} value={user.id}>
                        {user.display_name ?? user.email}
                      </option>
                    ))}
                  </select>
                  <Button
                    size="sm"
                    disabled={!choice[item.id] || busyId === item.id}
                    onClick={() => void assign(item.id)}
                  >
                    Zuweisen
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </DataTable>
      )}
    </>
  );
}
