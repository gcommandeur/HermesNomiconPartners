"use client";

import { useState } from "react";
import { ShieldOff } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorState } from "@/components/crm/error-state";
import { ErrorBanner } from "@/components/crm/error-banner";
import { Card, CardContent } from "@/components/ui/card";
import { apiPatch } from "@/lib/api/client";
import { useAdminUsersCache, useCurrentUser, invalidateAdminUsersCache } from "@/lib/api/hooks";
import type { AdminUser } from "@/lib/api/types";

export default function NutzerverwaltungPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const { data, isLoading, error, mutate: retry } = useAdminUsersCache(isAdmin);
  const users = data?.data ?? [];
  const [rowError, setRowError] = useState<string | null>(null);
  const [busyUserId, setBusyUserId] = useState<string | null>(null);

  async function toggleField(user: AdminUser, field: "is_admin" | "is_active") {
    setBusyUserId(user.id);
    setRowError(null);
    try {
      await apiPatch(`/users/${user.id}`, { [field]: !user[field] });
      await Promise.all([retry(), invalidateAdminUsersCache()]);
    } catch (exception) {
      setRowError(exception instanceof Error ? exception.message : "Änderung fehlgeschlagen.");
    } finally {
      setBusyUserId(null);
    }
  }

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
        <PageHeader eyebrow="Hermes" title="Nutzerverwaltung" />
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ShieldOff size={28} className="text-[#94A3B8]" />
            <p className="text-sm font-semibold text-[#F8FAFC]">Nur für Admins zugänglich</p>
            <p className="max-w-sm text-xs text-[#94A3B8]">
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
            <div key={index} className="h-14 animate-pulse rounded-lg bg-[#0D1B2E]" />
          ))}
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#102A4C] text-[11px] uppercase tracking-wider text-[#94A3B8]">
              <tr>
                <th className="p-3">Name</th>
                <th className="p-3">E-Mail</th>
                <th className="p-3">Admin</th>
                <th className="p-3">Aktiv</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {users.map((user) => (
                <tr key={user.id} className="hover:bg-[#203A5A]/25">
                  <td className="p-3 font-medium text-[#F8FAFC]">{user.display_name ?? "—"}</td>
                  <td className="p-3 text-[#CBD5E1]">{user.email}</td>
                  <td className="p-3">
                    <label className="inline-flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={user.is_admin}
                        disabled={busyUserId === user.id}
                        onChange={() => toggleField(user, "is_admin")}
                      />
                    </label>
                  </td>
                  <td className="p-3">
                    <label className="inline-flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={user.is_active}
                        disabled={busyUserId === user.id}
                        onChange={() => toggleField(user, "is_active")}
                      />
                    </label>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
