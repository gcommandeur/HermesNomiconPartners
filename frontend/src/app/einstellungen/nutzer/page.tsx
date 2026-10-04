"use client";

import { useState } from "react";
import { ShieldOff } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorState } from "@/components/crm/error-state";
import { ErrorBanner } from "@/components/crm/error-banner";
import { DataTable } from "@/components/crm/data-table";
import { Card, CardContent } from "@/components/ui/card";
import { apiPatch } from "@/lib/api/client";
import { useAdminUsersCache, useCurrentUser, invalidateAdminUsersCache } from "@/lib/api/hooks";
import type { AdminUser, UserRole } from "@/lib/api/types";

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: "member", label: "Mitarbeiter" },
  { value: "team_lead", label: "Teamleiter" },
  { value: "admin", label: "Admin" },
];

const selectClass =
  "h-9 rounded-md border border-white/15 bg-brand-surface px-2 text-sm text-brand-platinum focus:outline-none focus:ring-2 focus:ring-brand-accent/30 disabled:opacity-50";

export default function NutzerverwaltungPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const { data, isLoading, error, mutate: retry } = useAdminUsersCache(isAdmin);
  const users = data?.data ?? [];
  const [rowError, setRowError] = useState<string | null>(null);
  const [busyUserId, setBusyUserId] = useState<string | null>(null);

  async function patchUser(user: AdminUser, body: Record<string, unknown>) {
    setBusyUserId(user.id);
    setRowError(null);
    try {
      await apiPatch(`/users/${user.id}`, body);
      await Promise.all([retry(), invalidateAdminUsersCache()]);
    } catch (exception) {
      setRowError(exception instanceof Error ? exception.message : "Änderung fehlgeschlagen.");
    } finally {
      setBusyUserId(null);
    }
  }

  const toggleActive = (user: AdminUser) => patchUser(user, { is_active: !user.is_active });
  const changeRole = (user: AdminUser, role: UserRole) => patchUser(user, { role });
  // "" (Keine Zuordnung) -> explizit null, hebt die Zuordnung auf.
  const changeManager = (user: AdminUser, managerId: string) =>
    patchUser(user, { manager_id: managerId === "" ? null : managerId });

  if (meLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-14 animate-pulse rounded-lg bg-brand-surface" />
        ))}
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow="Hermes" title="Nutzerverwaltung" />
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ShieldOff size={28} className="text-brand-muted" />
            <p className="text-sm font-semibold text-brand-text">Nur für Admins zugänglich</p>
            <p className="max-w-sm text-xs text-brand-muted">
              Dieser Bereich ist der Nutzerverwaltung vorbehalten. Wende dich an einen Admin, falls
              du Zugriff benötigst.
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
      <PageHeader eyebrow="Hermes" title="Nutzerverwaltung" />
      <ErrorBanner message={rowError} className="mb-3" />
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-14 animate-pulse rounded-lg bg-brand-surface" />
          ))}
        </div>
      ) : (
        <DataTable headers={["Name", "E-Mail", "Rolle", "Teamleiter", "Aktiv"]}>
          {users.map((user) => {
            // Zur Auswahl: aktive Teamleiter (ohne den Nutzer selbst) - plus ein
            // bereits zugeordneter Teamleiter, auch wenn er inzwischen keiner
            // mehr ist, damit die aktuelle Zuordnung sichtbar bleibt.
            const managerOptions = users.filter(
              (candidate) =>
                candidate.id !== user.id &&
                ((candidate.role === "team_lead" && candidate.is_active) || candidate.id === user.manager_id),
            );
            const managerStale =
              user.manager_id !== null && !managerOptions.some((option) => option.id === user.manager_id);
            return (
              <tr key={user.id} className="hover:bg-brand-hover/25">
                <td className="px-4 py-3.5 font-medium text-brand-text">{user.display_name ?? "—"}</td>
                <td className="px-4 py-3.5 text-brand-soft">{user.email}</td>
                <td className="px-4 py-3.5">
                  <select
                    className={selectClass}
                    value={user.role}
                    disabled={busyUserId === user.id}
                    onChange={(event) => void changeRole(user, event.target.value as UserRole)}
                    aria-label={`Rolle von ${user.display_name ?? user.email}`}
                  >
                    {ROLE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-3.5">
                  {user.role === "admin" ? (
                    <span className="text-xs text-brand-muted" title="Admins sehen alle Prozesse">—</span>
                  ) : (
                    <>
                      <select
                        className={selectClass}
                        value={user.manager_id ?? ""}
                        disabled={busyUserId === user.id}
                        onChange={(event) => void changeManager(user, event.target.value)}
                        aria-label={`Teamleiter von ${user.display_name ?? user.email}`}
                      >
                        <option value="">Keine Zuordnung</option>
                        {managerOptions.map((option) => (
                          <option key={option.id} value={option.id}>
                            {option.display_name ?? option.email}
                            {option.role !== "team_lead" ? " (kein Teamleiter mehr)" : ""}
                          </option>
                        ))}
                      </select>
                      {managerStale && (
                        <p className="mt-1 text-[11px] text-brand-warning">Zugeordneter Teamleiter nicht in der Liste.</p>
                      )}
                    </>
                  )}
                </td>
                <td className="px-4 py-3.5">
                  <label className="inline-flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={user.is_active}
                      disabled={busyUserId === user.id}
                      onChange={() => toggleActive(user)}
                    />
                  </label>
                </td>
              </tr>
            );
          })}
        </DataTable>
      )}
    </>
  );
}
