"use client";

// NOMICON: Freischaltung der Ansichten je Mitarbeiter (nur Admins). Ansicht "Gesamt" nur für Admins.
import { useState } from "react";
import { ShieldOff } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorState } from "@/components/crm/error-state";
import { ErrorBanner } from "@/components/crm/error-banner";
import { DataTable } from "@/components/crm/data-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useCurrentUser } from "@/lib/api/hooks";
import {
  saveUserViews,
  saveViewDefaults,
  VIEW_DESCRIPTIONS,
  VIEW_LABELS,
  type UserViews,
  type ViewKey,
} from "@/lib/api/views";
import { refreshViews, useViewAccess, useViewDefaults } from "@/lib/api/views-hooks";
import { brand } from "@/lib/brand";

const ORDER: ViewKey[] = ["direct", "staffing", "management"];
const selectClass =
  "h-9 rounded-md border border-white/15 bg-brand-surface px-2 text-sm text-brand-platinum focus:outline-none focus:ring-2 focus:ring-brand-accent/30 disabled:opacity-50";

type Draft = { views: ViewKey[]; default_view: ViewKey };

export default function AnsichtenPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const { data, isLoading, error, mutate: retry } = useViewAccess(isAdmin);
  const { data: defaultsData } = useViewDefaults(isAdmin);
  const users = data?.data ?? [];
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const draftOf = (user: UserViews): Draft => drafts[user.user_id] ?? { views: user.views, default_view: user.default_view };
  const isAdminUser = (user: UserViews) => user.role === "admin";

  function toggle(user: UserViews, view: ViewKey) {
    const current = draftOf(user);
    const views = current.views.includes(view) ? current.views.filter((entry) => entry !== view) : [...current.views, view];
    const defaultView = views.includes(current.default_view) ? current.default_view : (ORDER.find((entry) => views.includes(entry)) ?? current.default_view);
    setDrafts((all) => ({ ...all, [user.user_id]: { views, default_view: defaultView } }));
  }

  async function save(user: UserViews) {
    const draft = draftOf(user);
    setBusy(user.user_id);
    setRowError(null);
    setMessage(null);
    try {
      await saveUserViews(user.user_id, { views: draft.views, default_view: draft.default_view });
      setDrafts((all) => Object.fromEntries(Object.entries(all).filter(([id]) => id !== user.user_id)));
      await Promise.all([retry(), refreshViews()]);
      setMessage(`Gespeichert: ${user.display_name ?? user.email}`);
    } catch (exception) {
      setRowError(exception instanceof Error ? exception.message : "Speichern fehlgeschlagen.");
    } finally {
      setBusy(null);
    }
  }

  async function toggleDefault(view: ViewKey) {
    const current = defaultsData?.data.views ?? ["direct"];
    const next = current.includes(view) ? current.filter((entry) => entry !== view) : [...current, view];
    if (next.length === 0) return;
    setRowError(null);
    try {
      await saveViewDefaults(next);
      await refreshViews();
      setMessage("Standard für neue Mitarbeiter gespeichert.");
    } catch (exception) {
      setRowError(exception instanceof Error ? exception.message : "Speichern fehlgeschlagen.");
    }
  }

  if (meLoading) return <div className="h-16 animate-pulse rounded-lg bg-brand-surface" />;

  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow={brand.appName} title="Ansichten freischalten" />
        <Card>
          <CardContent className="flex items-center gap-3 text-sm text-brand-muted">
            <ShieldOff size={18} /> Nur für Admins zugänglich.
          </CardContent>
        </Card>
      </>
    );
  }

  if (error) return <ErrorState onRetry={() => void retry()} />;

  const defaults = defaultsData?.data.views ?? ["direct"];

  return (
    <>
      <PageHeader eyebrow={brand.appName} title="Ansichten freischalten" />
      <p className="mb-4 max-w-2xl text-xs text-brand-muted">
        Die Rolle bestimmt, welche Datensätze ein Mitarbeiter sieht; die Ansicht bestimmt, welche Module.
        „Gesamt“ ist nur für Admins möglich und bleibt für sie immer an. Lohn und Marge sehen nur Admins.
      </p>
      <ErrorBanner message={rowError} className="mb-3" />
      {message && <p role="status" className="mb-3 rounded-md border border-brand-success/30 bg-brand-success-bg/45 px-3 py-2 text-xs text-brand-success-text">{message}</p>}
      <Card className="mb-5">
        <CardContent className="flex flex-wrap items-center gap-4 text-sm">
          <span className="font-medium text-brand-text">Standard für neue Mitarbeiter:</span>
          {(["direct", "staffing"] as ViewKey[]).map((view) => (
            <label key={view} className="flex items-center gap-2 text-brand-soft">
              <input type="checkbox" checked={defaults.includes(view)} onChange={() => void toggleDefault(view)} />
              {VIEW_LABELS[view]}
            </label>
          ))}
        </CardContent>
      </Card>
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-14 animate-pulse rounded-lg bg-brand-surface" />
          ))}
        </div>
      ) : (
        <DataTable headers={["Mitarbeiter", "Rolle", ...ORDER.map((view) => VIEW_LABELS[view]), "Startansicht", ""]}>
          {users.map((user) => {
            const draft = draftOf(user);
            const dirty = !isAdminUser(user) && (draft.views.join() !== user.views.join() || draft.default_view !== user.default_view);
            return (
              <tr key={user.user_id} className="hover:bg-brand-hover/25">
                <td className="px-4 py-3.5">
                  <p className="font-medium text-brand-text">{user.display_name ?? user.email}</p>
                  <p className="text-xs text-brand-muted">{user.email}{user.is_active ? "" : " · inaktiv"}</p>
                </td>
                <td className="px-4 py-3.5 text-brand-soft">{user.role === "admin" ? "Admin" : user.role === "team_lead" ? "Teamleiter" : "Mitarbeiter"}</td>
                {ORDER.map((view) => (
                  <td key={view} className="px-4 py-3.5">
                    <input
                      type="checkbox"
                      className="size-5"
                      checked={draft.views.includes(view)}
                      disabled={isAdminUser(user) || (view === "management") || busy === user.user_id}
                      onChange={() => toggle(user, view)}
                      aria-label={`${VIEW_LABELS[view]} für ${user.display_name ?? user.email}: ${VIEW_DESCRIPTIONS[view]}`}
                    />
                  </td>
                ))}
                <td className="px-4 py-3.5">
                  <select
                    className={selectClass}
                    value={draft.default_view}
                    disabled={isAdminUser(user) || busy === user.user_id}
                    onChange={(event) => setDrafts((all) => ({ ...all, [user.user_id]: { ...draft, default_view: event.target.value as ViewKey } }))}
                    aria-label={`Startansicht von ${user.display_name ?? user.email}`}
                  >
                    {ORDER.filter((view) => draft.views.includes(view)).map((view) => (
                      <option key={view} value={view}>{VIEW_LABELS[view]}</option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-3.5">
                  {!isAdminUser(user) && (
                    <Button size="sm" disabled={!dirty || busy === user.user_id} onClick={() => void save(user)}>
                      Speichern
                    </Button>
                  )}
                </td>
              </tr>
            );
          })}
        </DataTable>
      )}
    </>
  );
}
